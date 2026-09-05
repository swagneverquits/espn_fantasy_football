"""Persist normalized snapshots and track metadata changes."""

from __future__ import annotations

import hashlib
import json
import logging
import tempfile
from pathlib import Path

import pandas as pd

from fantasy_football.constants import PARQUET_DIR, TIMESTAMP_COL
from fantasy_football.snapshot import Snapshot
from fantasy_football.storage.parquet import (
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


def _load_state(path: Path) -> dict[str, str]:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(state, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in state.items()
        ):
            raise ValueError("Expected a metadata hash mapping")
        return state
    except FileNotFoundError:
        return {}
    except (ValueError, UnicodeError):
        logger.warning("Invalid metadata state at %s; rewriting metadata", path)
        return {}


def _save_state(path: Path, state: dict[str, str]) -> None:
    """Atomically publish state only after all metadata writes succeed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=path.parent, suffix=".tmp", delete=False
    ) as file:
        temporary = Path(file.name)
    try:
        temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


class ParquetSnapshotWriter:
    """Write one poll, suppressing unchanged metadata for this destination."""

    def __init__(self, store: ParquetObjectStore, state_path: str | Path) -> None:
        self.store = store
        self.state_path = Path(state_path)

    def write(self, snapshot: Snapshot) -> int:
        if snapshot.team_snapshots.empty:
            return 0
        for table in ("team_snapshots", "player_snapshots"):
            self._write_table(snapshot, table)
        self._write_changed_metadata(snapshot)
        return len(snapshot.team_snapshots)

    def _write_table(self, snapshot: Snapshot, table: str) -> None:
        self.store.write_frame(
            getattr(snapshot, table),
            provider=snapshot.provider,
            league_id=snapshot.league_id,
            season=snapshot.season,
            matchup_period=snapshot.matchup_period,
            table=table,
            timestamp=snapshot.timestamp,
        )

    def _write_changed_metadata(self, snapshot: Snapshot) -> None:
        state_path = self.state_path.with_name(
            f"{self.state_path.stem}_{snapshot.provider}_{snapshot.league_id}.json"
        )
        state = _load_state(state_path)
        changed_tables = []
        for table in ("team_metadata", "league_metadata", "player_metadata"):
            frame = getattr(snapshot, table)
            if frame.empty:
                continue
            fingerprint = _metadata_hash(frame)
            key = f"{snapshot.provider}/{snapshot.league_id}/{snapshot.season}/{snapshot.matchup_period}/{table}"
            if state.get(key) == fingerprint:
                continue
            self._write_table(snapshot, table)
            state[key] = fingerprint
            changed_tables.append(table)
        if changed_tables:
            _save_state(state_path, state)
            logger.info(
                "Metadata updated: provider=%s league=%s week=%s tables=%s",
                snapshot.provider,
                snapshot.league_id,
                snapshot.matchup_period,
                ",".join(changed_tables),
            )


def build_writer(
    root: str | Path = PARQUET_DIR, bucket: str | None = None
) -> ParquetSnapshotWriter:
    """Build a local or GCS writer with destination-specific metadata state."""
    uploader: ObjectUploader = (
        GCSObjectUploader(bucket) if bucket else LocalObjectUploader(root)
    )
    destination = f"gcs:{bucket}" if bucket else f"local:{Path(root).resolve()}"
    namespace = hashlib.sha256(destination.encode()).hexdigest()[:16]
    return ParquetSnapshotWriter(
        ParquetObjectStore(uploader), Path(root) / f".metadata_hashes_{namespace}.json"
    )
