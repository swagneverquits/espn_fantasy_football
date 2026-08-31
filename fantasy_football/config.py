"""Shared environment, paths, and league configuration."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

SEASON = "2025"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
RESULTS_DIR = DATA_DIR / "results"
PLOTS_DIR = DATA_DIR / "plots"
SCRATCH_DIR = PROJECT_ROOT / "scratch"


def _required_int_env(name: str) -> int:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"{name} must be set in environment variables or .env")
    return int(value)


LEAGUE_IDS = {
    "college": _required_int_env("ESPN_LEAGUE_ID_COLLEGE"),
    "high_school": _required_int_env("ESPN_LEAGUE_ID_HIGH_SCHOOL"),
    "charter": _required_int_env("ESPN_LEAGUE_ID_CHARTER"),
}
