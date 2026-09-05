"""Normalized Parquet persistence and reads for live fantasy snapshots."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)
WORKER_PROCESS = os.getenv("FANTASY_FOOTBALL_WORKER") == "1"

from fantasy_football.constants import (
    LEAGUE_ID_COL,
    MATCHUP_ID_COL,
    MATCHUP_PERIOD_COL,
    PARQUET_DIR,
    PROVIDER_COL,
    SEASON_COL,
    TEAM_ID_COL,
    TIMESTAMP_COL,
)
from fantasy_football.storage.normalization import player_data, unix_seconds
from fantasy_football.storage.objects import (
    GCSObjectUploader,
    LocalObjectUploader,
    ObjectUploader,
    ParquetObjectStore,
)


def _metadata_hash(frame: pd.DataFrame) -> str:
    frame = frame.drop(columns=[TIMESTAMP_COL], errors="ignore")
    payload = (
        frame.sort_index(axis=1)
        .sort_values(list(frame.columns))
        .to_json(orient="records", date_format="iso")
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _snapshot_frames(
    frame: pd.DataFrame,
    *,
    provider: str,
    league_id: str | int,
    season: int,
    matchup_period: int,
    data: dict,
) -> dict[str, pd.DataFrame]:
    output = frame.reset_index()
    timestamp = output["time"].map(unix_seconds)
    poll_timestamp = int(timestamp.iloc[0])
    team_rows = pd.DataFrame(
        {
            PROVIDER_COL: provider,
            LEAGUE_ID_COL: str(league_id),
            SEASON_COL: season,
            MATCHUP_PERIOD_COL: matchup_period,
            MATCHUP_ID_COL: output["Matchup"],
            TIMESTAMP_COL: timestamp,
            TEAM_ID_COL: output[TEAM_ID_COL],
            "opponent_id": output["opponent_id"],
            "score_live": output["TotalPointsLive"],
            "projected_live": output["Projected"].round(2),
            "win_probability": output["WinChance"],
        }
    )
    player_rows, player_meta = player_data(
        data, provider, league_id, season, matchup_period, poll_timestamp
    )
    players = pd.DataFrame(
        player_rows,
        columns=[
            PROVIDER_COL,
            LEAGUE_ID_COL,
            SEASON_COL,
            MATCHUP_PERIOD_COL,
            MATCHUP_ID_COL,
            TIMESTAMP_COL,
            TEAM_ID_COL,
            "player_id",
            "lineup_slot_id",
            "points_live",
            "projected",
            "ceiling",
            "projection_spread",
        ],
    )
    if provider == "espn":
        team_meta = [
            (
                provider,
                str(league_id),
                season,
                matchup_period,
                team.get("id"),
                team.get("name"),
                team.get("logo"),
                poll_timestamp,
            )
            for team in data.get("teams", [])
        ]
    else:
        users = {str(user.get("user_id")): user for user in data.get("users", [])}
        team_meta = []
        for roster in data.get("rosters", []):
            user = users.get(str(roster.get("owner_id")), {})
            metadata = user.get("metadata") or {}
            team_meta.append(
                (
                    provider,
                    str(league_id),
                    season,
                    matchup_period,
                    roster.get("roster_id"),
                    metadata.get("team_name") or user.get("display_name"),
                    metadata.get("avatar") or user.get("avatar"),
                    poll_timestamp,
                )
            )
    teams = pd.DataFrame(
        team_meta,
        columns=[
            PROVIDER_COL,
            LEAGUE_ID_COL,
            SEASON_COL,
            MATCHUP_PERIOD_COL,
            TEAM_ID_COL,
            "team_name",
            "logo_url",
            TIMESTAMP_COL,
        ],
    )
    league_name = (data.get("league") or {}).get("name") or data.get("name")
    if provider == "espn":
        league_name = (data.get("settings") or {}).get("name") or league_name
    league = pd.DataFrame(
        [
            {
                PROVIDER_COL: provider,
                LEAGUE_ID_COL: str(league_id),
                SEASON_COL: season,
                "league_name": league_name,
                TIMESTAMP_COL: poll_timestamp,
            }
        ]
    )
    player_metadata = pd.DataFrame(
        player_meta,
        columns=[
            PROVIDER_COL,
            LEAGUE_ID_COL,
            SEASON_COL,
            MATCHUP_PERIOD_COL,
            "player_id",
            TIMESTAMP_COL,
            "player_name",
            "position",
        ],
    )
    return {
        "team_snapshots": team_rows,
        "player_snapshots": players,
        "team_metadata": teams,
        "league_metadata": league,
        "player_metadata": player_metadata,
    }


class ParquetSnapshotWriter:
    """Write one poll to Parquet, uploading each completed object immediately."""

    def __init__(self, store: ParquetObjectStore, state_path: str | Path):
        self.store = store
        self.state_path = Path(state_path)

    def write(
        self,
        frame: pd.DataFrame,
        *,
        provider: str,
        league_id: str | int,
        season: int,
        matchup_period: int,
        data: dict,
    ) -> int:
        frames = _snapshot_frames(
            frame,
            provider=provider,
            league_id=league_id,
            season=season,
            matchup_period=matchup_period,
            data=data,
        )
        timestamp = int(frames["team_snapshots"][TIMESTAMP_COL].iloc[0])
        for table in ("team_snapshots", "player_snapshots"):
            self.store.write_frame(
                frames[table],
                provider=provider,
                league_id=league_id,
                season=season,
                matchup_period=matchup_period,
                table=table,
                timestamp=timestamp,
            )
        self._write_changed_metadata(
            frames, provider, league_id, season, matchup_period, timestamp
        )
        return len(frames["team_snapshots"])

    def _write_changed_metadata(
        self,
        frames: dict[str, pd.DataFrame],
        provider: str,
        league_id: str | int,
        season: int,
        matchup_period: int,
        timestamp: int,
    ) -> None:
        state_path = self.state_path.with_name(
            f"{self.state_path.stem}_{provider}_{league_id}.json"
        )
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            if not isinstance(state, dict):
                raise ValueError("Expected a metadata hash object")
        except FileNotFoundError:
            state = {}
        except (ValueError, UnicodeError):
            logger.warning(
                "Invalid metadata state at %s; rewriting metadata", state_path
            )
            state = {}
        changed = False
        changed_tables = []
        for table in ("team_metadata", "league_metadata", "player_metadata"):
            frame = frames[table]
            if frame.empty:
                continue
            fingerprint = _metadata_hash(frame)
            key = f"{provider}/{league_id}/{season}/{matchup_period}/{table}"
            if state.get(key) == fingerprint:
                continue
            self.store.write_frame(
                frame,
                provider=provider,
                league_id=league_id,
                season=season,
                matchup_period=matchup_period,
                table=table,
                timestamp=timestamp,
            )
            state[key] = fingerprint
            changed = True
            changed_tables.append(table)
        if changed:
            state_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=state_path.parent,
                suffix=".tmp",
                delete=False,
            ) as file:
                temporary = Path(file.name)
            try:
                temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
                temporary.replace(state_path)
            finally:
                temporary.unlink(missing_ok=True)
            logger.info(
                "Metadata updated: provider=%s league=%s week=%s tables=%s",
                provider,
                league_id,
                matchup_period,
                ",".join(changed_tables),
            )


def build_writer(
    root: str | Path = PARQUET_DIR, bucket: str | None = None
) -> ParquetSnapshotWriter:
    """Build a local or GCS writer with destination-specific metadata state."""
    local = LocalObjectUploader(root)
    uploader: ObjectUploader = local
    if bucket:
        uploader = GCSObjectUploader(bucket)
    destination = f"gcs:{bucket}" if bucket else f"local:{Path(root).resolve()}"
    namespace = hashlib.sha256(destination.encode()).hexdigest()[:16]
    return ParquetSnapshotWriter(
        ParquetObjectStore(uploader), Path(root) / f".metadata_hashes_{namespace}.json"
    )


def configured_writer(storage_mode: str = "local") -> ParquetSnapshotWriter:
    """Build a writer for the explicitly selected storage destination."""
    if storage_mode not in {"local", "gcs"}:
        raise ValueError("storage_mode must be 'local' or 'gcs'")
    if storage_mode == "local":
        if not WORKER_PROCESS:
            logger.info("Snapshot destination: local path=%s", PARQUET_DIR)
        return build_writer()

    bucket = os.getenv("GCS_BUCKET")
    if not bucket:
        raise ValueError("GCS_BUCKET is required when storage_mode='gcs'")
    if not WORKER_PROCESS:
        logger.info("Snapshot destination: GCS bucket=%s", bucket)
    return build_writer(bucket=bucket)
