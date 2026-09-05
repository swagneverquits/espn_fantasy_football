"""Incrementally synchronize Parquet objects from Google Cloud Storage."""

from __future__ import annotations

import logging
import tempfile
from collections.abc import Sequence
from pathlib import Path

from fantasy_football.constants import PARQUET_TABLES

logger = logging.getLogger(__name__)


def sync_parquet_prefix(
    bucket_name: str,
    *,
    provider: str,
    league_id: str | int,
    season: int,
    matchup_period: int,
    output_dir: str | Path,
    tables: Sequence[str] | None = None,
) -> int:
    """Download only new selected Parquet objects into a local cache."""
    from google.cloud import storage

    selected_tables = set(tables or PARQUET_TABLES)
    unknown_tables = selected_tables.difference(PARQUET_TABLES)
    if unknown_tables:
        raise ValueError(f"Unknown Parquet table(s): {sorted(unknown_tables)}")

    prefix = (
        f"provider={provider}/league={league_id}/season={season}/"
        f"week={matchup_period}/"
    )
    root = Path(output_dir)
    downloaded = 0
    skipped = 0
    ignored = 0
    client = storage.Client()
    for blob in client.bucket(bucket_name).list_blobs(prefix=prefix):
        relative = blob.name[len(prefix) :]
        table = relative.split("/", maxsplit=1)[0]
        if table not in selected_tables or not relative.startswith(f"{table}/"):
            ignored += 1
            continue
        destination = root / blob.name
        if destination.exists() and destination.stat().st_size == blob.size:
            skipped += 1
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Publish only complete downloads; interrupted files are safe to retry.
        with tempfile.NamedTemporaryFile(
            dir=destination.parent, suffix=".part", delete=False
        ) as file:
            temporary = Path(file.name)
        try:
            blob.download_to_filename(temporary)
            if blob.size is not None and temporary.stat().st_size != blob.size:
                raise OSError(f"Incomplete download: {blob.name}")
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        downloaded += 1

    logger.info(
        "Sync complete: bucket=%s downloaded=%d skipped=%d ignored=%d tables=%s",
        bucket_name,
        downloaded,
        skipped,
        ignored,
        ",".join(sorted(selected_tables)),
    )
    return downloaded
