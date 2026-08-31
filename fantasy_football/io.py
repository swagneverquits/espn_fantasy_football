"""Shared filesystem and tabular data-loading helpers."""

from pathlib import Path

import pandas as pd

from fantasy_football.config import PLOTS_DIR, RESULTS_DIR, SEASON


def get_results_path(league: str, week: int) -> Path:
    """Generate a results file path using the configured season."""
    results_dir = RESULTS_DIR / SEASON / league
    results_dir.mkdir(parents=True, exist_ok=True)
    return results_dir / f"week_{week}.csv"


def get_results_file(season: int, week: int, league: str) -> Path:
    """Return the results CSV path for a season, week, and league."""
    return Path(RESULTS_DIR) / str(season) / league / f"week_{week}.csv"


def get_plots_dir(season: int, week: int, league: str) -> Path:
    """Ensure and return the generated-plot directory."""
    plots_dir = Path(PLOTS_DIR) / str(season) / league / f"week_{week}"
    plots_dir.mkdir(parents=True, exist_ok=True)
    return plots_dir


def load_results(season: int, week: int, league: str) -> pd.DataFrame:
    """Load and index a collected matchup snapshot CSV."""
    results_file = get_results_file(season, week, league)
    if not results_file.exists():
        raise FileNotFoundError(f"Results file not found: {results_file}")
    try:
        df = pd.read_csv(results_file)
    except pd.errors.EmptyDataError as exc:
        raise ValueError(f"Results file is empty: {results_file}") from exc
    if df.empty:
        raise ValueError(f"Results file has no rows: {results_file}")
    df["time"] = pd.to_datetime(df["time"])
    df["date"] = df["time"].dt.date
    return df.set_index(["time", "team"])
