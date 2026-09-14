"""Incrementally synchronize Parquet objects from Google Cloud Storage."""

from __future__ import annotations

import logging
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from google.cloud.storage import Blob

from fantasy_football.constants import PARQUET_TABLES
from fantasy_football.storage.parquet import partition_prefix

logger = logging.getLogger(__name__)


def sync_parquet_prefix(
    bucket_name: str,
    *,
    provider: str,
    league_id: str | int,
    season: int,
    matchup_period: int | None,
    output_dir: str | Path,
    tables: Sequence[str] | None = None,
    progress: Callable[[str, int, int | None], None] | None = None,
) -> int:
    """Download selected Parquet objects into a local cache incrementally."""
    from google.cloud import storage

    selected_tables = set(tables or PARQUET_TABLES)
    unknown_tables = selected_tables.difference(PARQUET_TABLES)
    if unknown_tables:
        raise ValueError(f"Unknown Parquet table(s): {sorted(unknown_tables)}")

    prefix = (
        partition_prefix(provider, league_id, season, matchup_period)
        if matchup_period is not None
        else f"provider={provider}/league={league_id}/season={season}/"
    )
    root = Path(output_dir)
    downloaded = 0
    skipped = 0
    ignored = 0
    latest = None
    if progress:
        progress("Syncing", downloaded, latest)
    client = storage.Client()
    for blob in client.bucket(bucket_name).list_blobs(prefix=prefix):
        relative = blob.name[len(prefix) :]
        parts = relative.split("/")
        if matchup_period is None:
            if len(parts) < 3 or not parts[0].startswith("week="):
                ignored += 1
                continue
            table = parts[1]
            table_relative = "/".join(parts[1:])
        else:
            table = parts[0]
            table_relative = relative
        if table not in selected_tables or not table_relative.startswith(
            f"{table}/"
        ):
            ignored += 1
            continue
        destination = root / blob.name
        if destination.exists() and destination.stat().st_size == blob.size:
            skipped += 1
        else:
            _download(blob, destination)
            downloaded += 1
        # Snapshot object names carry the capture time, not the upload time.
        if table == "team_snapshots":
            try:
                stamp = int(Path(blob.name).stem.removeprefix("timestamp="))
                latest = max(latest or stamp, stamp)
            except ValueError:
                pass
        if progress:
            progress("Syncing", downloaded, latest)

    if progress:
        progress("Synced", downloaded, latest)
    else:
        logger.info(
            "Sync complete: bucket=%s downloaded=%d skipped=%d ignored=%d",
            bucket_name,
            downloaded,
            skipped,
            ignored,
        )
    return downloaded


def _download(blob: Blob, destination: Path) -> None:
    """Publish a complete download atomically."""
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
