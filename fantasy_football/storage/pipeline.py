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

from fantasy_football.constants import PARQUET_DIR, TIMESTAMP_COL
from fantasy_football.snapshot import Snapshot
from fantasy_football.storage.objects import (
    GCSObjectUploader,
    LocalObjectUploader,
    ObjectUploader,
    ParquetObjectStore,
)

logger = logging.getLogger(__name__)


def _metadata_hash(frame: pd.DataFrame) -> str:
    frame = frame.drop(columns=[TIMESTAMP_COL], errors="ignore")
    payload = (
        frame.sort_index(axis=1)
        .sort_values(list(frame.columns))
        .to_json(orient="records", date_format="iso")
    )
    return hashlib.sha256(payload.encode()).hexdigest()


class ParquetSnapshotWriter:
    """Write one poll to Parquet, uploading each completed object immediately."""

    def __init__(self, store: ParquetObjectStore, state_path: str | Path):
        self.store = store
        self.state_path = Path(state_path)

    def write(self, snapshot: Snapshot) -> int:
        """Persist normalized tables without interpreting provider payloads."""
        frames = snapshot.frames
        if snapshot.team_snapshots.empty:
            return 0
        for table in ("team_snapshots", "player_snapshots"):
            self.store.write_frame(
                frames[table],
                provider=snapshot.provider,
                league_id=snapshot.league_id,
                season=snapshot.season,
                matchup_period=snapshot.matchup_period,
                table=table,
                timestamp=snapshot.timestamp,
            )
        self._write_changed_metadata(
            frames,
            snapshot.provider,
            snapshot.league_id,
            snapshot.season,
            snapshot.matchup_period,
            snapshot.timestamp,
        )
        return len(snapshot.team_snapshots)

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
        if os.getenv("FANTASY_FOOTBALL_WORKER") != "1":
            logger.info("Snapshot destination: local path=%s", PARQUET_DIR)
        return build_writer()

    bucket = os.getenv("GCS_BUCKET")
    if not bucket:
        raise ValueError("GCS_BUCKET is required when storage_mode='gcs'")
    if os.getenv("FANTASY_FOOTBALL_WORKER") != "1":
        logger.info("Snapshot destination: GCS bucket=%s", bucket)
    return build_writer(bucket=bucket)
