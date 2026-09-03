"""Normalized Parquet persistence and reads for live fantasy snapshots."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

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
from fantasy_football.normalization import player_data, unix_seconds
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
            f".metadata_hashes_{provider}_{league_id}.json"
        )
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
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
            state_path.write_text(json.dumps(state, indent=2))
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
    """Build a local writer, optionally uploading each object to GCS as well."""
    local = LocalObjectUploader(root)
    uploader: ObjectUploader = local
    if bucket:
        uploader = GCSObjectUploader(bucket)
    return ParquetSnapshotWriter(
        ParquetObjectStore(uploader), Path(root) / ".metadata_hashes.json"
    )


def configured_writer() -> ParquetSnapshotWriter:
    """Build the writer from the VM environment configuration."""
    bucket = os.getenv("GCS_BUCKET")
    if bucket:
        logger.info("Snapshot destination: GCS bucket=%s", bucket)
    else:
        logger.info("Snapshot destination: local path=%s", PARQUET_DIR)
    return build_writer(bucket=bucket)


def load_matchup_results_from_parquet(
    root: str | Path,
    *,
    provider: str,
    league_id: str | int,
    season: int,
    matchup_period: int,
) -> pd.DataFrame:
    """Load normalized matchup rows from local Parquet objects with pandas."""
    root = Path(root)
    prefix = (
        root
        / f"provider={provider}"
        / f"league={league_id}"
        / f"season={season}"
        / f"week={matchup_period}"
    )

    def files_for(table: str) -> list[Path]:
        compacted = [path for path in (prefix / f"{table}.pq",) if path.exists()]
        if compacted:
            return compacted
        return sorted((prefix / table).glob("*.pq"))

    snapshot_files = files_for("team_snapshots")
    if not snapshot_files:
        raise FileNotFoundError(f"No Parquet snapshots found under {prefix}")
    snapshots = pd.concat(
        (pd.read_parquet(path) for path in snapshot_files), ignore_index=True
    )
    team_files = files_for("team_metadata")
    league_files = files_for("league_metadata")
    if team_files:
        teams = pd.concat(
            (pd.read_parquet(path) for path in team_files), ignore_index=True
        )
        teams = teams.sort_values(TIMESTAMP_COL).drop_duplicates(
            [PROVIDER_COL, LEAGUE_ID_COL, SEASON_COL, MATCHUP_PERIOD_COL, TEAM_ID_COL],
            keep="last",
        )
        snapshots = snapshots.merge(
            teams[[TEAM_ID_COL, "team_name"]], on=TEAM_ID_COL, how="left"
        )
    else:
        snapshots["team_name"] = pd.NA
    if league_files:
        leagues = pd.concat(
            (pd.read_parquet(path) for path in league_files), ignore_index=True
        )
        league_name = (
            leagues.sort_values(TIMESTAMP_COL)["league_name"].dropna().iloc[-1]
        )
    else:
        league_name = None
    result = pd.DataFrame(
        {
            "time": pd.to_datetime(
                snapshots[TIMESTAMP_COL], unit="s", utc=True
            ).dt.tz_convert("America/New_York"),
            "team": snapshots["team_name"].fillna(snapshots[TEAM_ID_COL].astype(str)),
            "Matchup": snapshots[MATCHUP_ID_COL],
            "MatchupPeriod": snapshots[MATCHUP_PERIOD_COL],
            "Score": snapshots["score_live"],
            "Projected": snapshots["projected_live"],
            "WinChance": snapshots["win_probability"],
            "league_name": league_name,
        }
    )
    return result.sort_values(
        ["time", "Matchup", TEAM_ID_COL] if TEAM_ID_COL in result else ["time"]
    ).set_index(["time", "team"])
