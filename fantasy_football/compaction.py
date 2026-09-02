"""Compact raw polling objects into one Parquet object per table and week."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterable
from pathlib import Path

import pandas as pd

from fantasy_football.constants import (
    LEAGUE_ID_COL,
    MATCHUP_PERIOD_COL,
    PROVIDER_COL,
    SEASON_COL,
    TEAM_ID_COL,
    TIMESTAMP_COL,
)

TABLES = (
    "team_snapshots",
    "player_snapshots",
    "team_metadata",
    "league_metadata",
    "player_metadata",
)

METADATA_KEYS = {
    "team_metadata": (
        PROVIDER_COL,
        LEAGUE_ID_COL,
        SEASON_COL,
        MATCHUP_PERIOD_COL,
        TEAM_ID_COL,
    ),
    "league_metadata": (PROVIDER_COL, LEAGUE_ID_COL, SEASON_COL),
    "player_metadata": (
        PROVIDER_COL,
        LEAGUE_ID_COL,
        SEASON_COL,
        MATCHUP_PERIOD_COL,
        "player_id",
    ),
}


def compact_frames(frames: Iterable[pd.DataFrame], table: str) -> pd.DataFrame:
    """Combine raw frames and retain only the latest metadata values."""
    combined = pd.concat(frames, ignore_index=True)
    keys = METADATA_KEYS.get(table)
    if keys:
        combined = combined.sort_values(TIMESTAMP_COL).drop_duplicates(
            list(keys), keep="last"
        )
    return combined.reset_index(drop=True)


def compact_gcs_week(
    bucket_name: str,
    *,
    provider: str,
    league_id: str | int,
    season: int,
    matchup_period: int,
) -> dict[str, str]:
    """Compact one GCS week; raw objects are retained."""
    from google.cloud import storage

    prefix = (
        f"provider={provider}/league={league_id}/season={season}/week={matchup_period}/"
    )
    project = os.getenv("GOOGLE_CLOUD_PROJECT") or None
    bucket = storage.Client(project=project).bucket(bucket_name)
    blobs_by_table: dict[str, list] = {table: [] for table in TABLES}
    for blob in bucket.list_blobs(prefix=prefix):
        relative = blob.name[len(prefix) :]
        parts = relative.split("/")
        if len(parts) == 2 and parts[0] in blobs_by_table and parts[1].endswith(".pq"):
            blobs_by_table[parts[0]].append(blob)

    outputs: dict[str, str] = {}
    with tempfile.TemporaryDirectory() as directory:
        directory_path = Path(directory)
        for table, blobs in blobs_by_table.items():
            if not blobs:
                continue
            frames = []
            for index, blob in enumerate(blobs):
                source = directory_path / f"{table}_{index}.pq"
                blob.download_to_filename(source)
                frames.append(pd.read_parquet(source))
            output = directory_path / f"{table}.pq"
            compact_frames(frames, table).to_parquet(
                output, index=False, compression="zstd"
            )
            object_name = f"{prefix}{table}.pq"
            bucket.blob(object_name).upload_from_filename(output)
            outputs[table] = object_name
    return outputs
