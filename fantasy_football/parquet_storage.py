"""Write normalized snapshot frames as local or Google Cloud Storage objects."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Protocol

import pandas as pd


class ObjectUploader(Protocol):
    """Minimal interface needed to upload a completed Parquet object."""

    def upload(self, source: Path, object_name: str) -> None: ...


class LocalObjectUploader:
    """Store objects beneath a local directory, preserving their object paths."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def upload(self, source: Path, object_name: str) -> None:
        destination = self.root / object_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.replace(destination)


class GCSObjectUploader:
    """Upload objects to a GCS bucket using Application Default Credentials."""

    def __init__(self, bucket_name: str):
        from google.cloud import storage

        self.bucket = storage.Client().bucket(bucket_name)

    def upload(self, source: Path, object_name: str) -> None:
        self.bucket.blob(object_name).upload_from_filename(source)


class ParquetObjectStore:
    """Persist one completed Parquet object per polling result."""

    def __init__(self, uploader: ObjectUploader):
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
            f"provider={provider}/league={league_id}/season={season}/"
            f"week={matchup_period}/{table}/timestamp={timestamp}.pq"
        )
        with tempfile.NamedTemporaryFile(suffix=".pq", delete=False) as file:
            temporary_path = Path(file.name)
        try:
            frame.to_parquet(temporary_path, index=False, compression="zstd")
            self.uploader.upload(temporary_path, object_name)
        finally:
            temporary_path.unlink(missing_ok=True)
        return object_name
