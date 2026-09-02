"""Synchronize selected Parquet objects from Google Cloud Storage."""

from __future__ import annotations

from pathlib import Path


def sync_parquet_prefix(
    bucket_name: str,
    *,
    provider: str,
    league_id: str | int,
    season: int,
    matchup_period: int,
    output_dir: str | Path,
) -> int:
    """Download one league/week prefix into a local Parquet cache."""
    from google.cloud import storage

    prefix = (
        f"provider={provider}/league={league_id}/season={season}/"
        f"week={matchup_period}/"
    )
    root = Path(output_dir)
    client = storage.Client()
    blobs = list(client.bucket(bucket_name).list_blobs(prefix=prefix))
    for blob in blobs:
        destination = root / blob.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        blob.download_to_filename(destination)
    return len(blobs)
