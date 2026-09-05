"""Write normalized snapshot frames as local or Google Cloud Storage objects."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Protocol

import pandas as pd


def partition_prefix(
    provider: str, league_id: str | int, season: int, matchup_period: int
) -> str:
    """Return the shared league/week object prefix, including its trailing slash."""
    return (
        f"provider={provider}/league={league_id}/season={season}/week={matchup_period}/"
    )


class ObjectUploader(Protocol):
    """Minimal interface needed to upload a completed Parquet object."""

    def upload(self, source: Path, object_name: str) -> None: ...


class LocalObjectUploader:
    """Store objects beneath a local directory, preserving their object paths."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def upload(self, source: Path, object_name: str) -> None:
        destination = self.root / object_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Stage beside the destination so the final rename stays on one filesystem.
        with tempfile.NamedTemporaryFile(
            dir=destination.parent, suffix=".tmp", delete=False
        ) as file:
            temporary = Path(file.name)
        try:
            shutil.copyfile(source, temporary)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)


class GCSObjectUploader:
    """Upload objects to a GCS bucket using Application Default Credentials."""

    def __init__(self, bucket_name: str) -> None:
        from google.cloud import storage

        self.bucket = storage.Client().bucket(bucket_name)

    def upload(self, source: Path, object_name: str) -> None:
        self.bucket.blob(object_name).upload_from_filename(source)


class ParquetObjectStore:
    """Persist one completed Parquet object per polling result."""

    def __init__(self, uploader: ObjectUploader) -> None:
        self.uploader = uploader

    def write_frame(
        self,
        frame: pd.DataFrame,
        *,
        provider: str,
        league_id: str | int,
        season: int,
        matchup_period: int,
        table: str,
        timestamp: int,
    ) -> str:
        """Write and upload one uniquely named Parquet object."""
        object_name = (
            partition_prefix(provider, league_id, season, matchup_period)
            + f"{table}/timestamp={timestamp}.pq"
        )
        with tempfile.NamedTemporaryFile(suffix=".pq", delete=False) as file:
            temporary_path = Path(file.name)
        try:
            frame.to_parquet(temporary_path, index=False, compression="zstd")
            self.uploader.upload(temporary_path, object_name)
        finally:
            temporary_path.unlink(missing_ok=True)
        return object_name
