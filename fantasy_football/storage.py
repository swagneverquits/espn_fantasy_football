"""Shared snapshot storage for all provider scrapers."""

from pathlib import Path

import pandas as pd

DEFAULT_INTERVAL_SECONDS = 30
DEFAULT_RETRY_SECONDS = 30


def write_snapshot(path: Path, frame: pd.DataFrame) -> int:
    """Append a standardized snapshot frame to a CSV."""
    output = frame.reset_index()
    output.to_csv(path, mode="a", header=not path.exists(), index=False)
    return len(output)
