from pathlib import Path

from src.config import RESULTS_DIR, SEASON, PLOTS_DIR


def get_results_path(league_id: int, week: int) -> Path:
    """Generate results file path based on current date."""

    results_dir = RESULTS_DIR / SEASON / str(league_id)
    results_dir.mkdir(parents=True, exist_ok=True)
    return results_dir / f"week_{week}.csv"


def dump_html(driver, filename="page_dump.html"):
    with open(filename, "w", encoding="utf-8") as f:
        f.write(driver.page_source)
    print(f"HTML dumped to {filename}")


def get_results_file(season: int, week: int, league_id: int) -> Path:
    """Return the path to the results CSV for a given week."""
    return Path(RESULTS_DIR) / str(season) / str(league_id) / f"week_{week}.csv"

def get_plots_dir(season: int, week: int, league_id: int) -> Path:
    """Ensure and return the directory for plots for a given week."""
    plots_dir = Path(PLOTS_DIR) / str(season) / str(league_id) / f"week_{week}"
    plots_dir.mkdir(parents=True, exist_ok=True)
    return plots_dir
