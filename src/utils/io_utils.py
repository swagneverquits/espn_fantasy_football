from pathlib import Path

import pandas as pd

from src.config import PLOTS_DIR, RESULTS_DIR, SEASON


def get_results_path(league: str, week: int) -> Path:
    """Generate results file path based on current date."""

    results_dir = RESULTS_DIR / SEASON / league
    results_dir.mkdir(parents=True, exist_ok=True)
    return results_dir / f"week_{week}.csv"


def get_results_file(season: int, week: int, league: str) -> Path:
    """Return the path to the results CSV for a given week."""
    return Path(RESULTS_DIR) / str(season) / league / f"week_{week}.csv"


def get_plots_dir(season: int, week: int, league: str) -> Path:
    """Ensure and return the directory for plots for a given week."""
    plots_dir = Path(PLOTS_DIR) / str(season) / league / f"week_{week}"
    plots_dir.mkdir(parents=True, exist_ok=True)
    return plots_dir


def load_results(season: int, week: int, league: str) -> pd.DataFrame:
    """
    Load results CSV for a given season, week, and league.
    Parses datetime and sets a proper index.
    """
    results_file = Path(RESULTS_DIR) / str(season) / league / f"week_{week}.csv"
    df = pd.read_csv(results_file)
    df["time"] = pd.to_datetime(df["time"])
    df["date"] = df["time"].dt.date
    return df.set_index(["time", "team"])


def dump_html(driver, filename="page_dump.html"):
    # Point to sandbox folder
    sandbox_dir = Path(__file__).resolve().parent.parent / "__sandbox__"
    sandbox_dir.mkdir(parents=True, exist_ok=True)

    filepath = sandbox_dir / filename
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(driver.page_source)

    print(f"HTML dumped to {filepath}")
