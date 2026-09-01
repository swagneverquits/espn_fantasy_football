"""Shared paths and league configuration."""

import tomllib
from pathlib import Path

SEASON = "2025"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
RESULTS_DIR = DATA_DIR / "results"
PLOTS_DIR = DATA_DIR / "plots"
SCRATCH_DIR = PROJECT_ROOT / "scratch"
LEAGUE_CONFIG_PATH = PROJECT_ROOT / "config" / "leagues.toml"


def _load_leagues() -> dict:
    if not LEAGUE_CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Create {LEAGUE_CONFIG_PATH} from leagues.toml.example"
        )
    with LEAGUE_CONFIG_PATH.open("rb") as file:
        config = tomllib.load(file)
    if not config.get("espn"):
        raise ValueError("At least one [espn] league must be configured")
    if not config.get("sleeper"):
        raise ValueError("At least one [sleeper] league must be configured")
    return config


_LEAGUES = _load_leagues()
ESPN_LEAGUES = {name: str(league_id) for name, league_id in _LEAGUES["espn"].items()}
LEAGUE_IDS = {name: int(league_id) for name, league_id in ESPN_LEAGUES.items()}
SLEEPER_LEAGUES = {
    name: str(league_id) for name, league_id in _LEAGUES["sleeper"].items()
}
