"""
Configuration for the Fantasy Football scraper.
Centralizes secrets, paths, and league URLs.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load variables from a .env file if present (local dev convenience)
load_dotenv()

# ------------------------
# Secrets / Credentials
# ------------------------
SEASON = "2025"
EMAIL = os.getenv("ESPN_EMAIL")
PASSWORD = os.getenv("ESPN_PASSWORD")

if not EMAIL or not PASSWORD:
    raise ValueError(
        "❌ ESPN_EMAIL and ESPN_PASSWORD must be set in environment variables or .env"
    )


# ------------------------
# Paths
# ------------------------

# Path to ChromeDriver binary
DRIVER_PATH = os.getenv("CHROMEDRIVER_PATH", "/usr/local/bin/chromedriver")

# Project root = the repo root, one level above this file’s parent
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Data directory always under /data
DATA_DIR = PROJECT_ROOT / "data"

# Raw scraped CSV snapshots
RAW_DATA_DIR = DATA_DIR / "raw"

# Processed CSV snapshots used by analysis
PROCESSED_DATA_DIR = DATA_DIR / "processed"

# Backward-compatible results directory for existing local outputs
RESULTS_DIR = DATA_DIR / "results"

# Plots directory
PLOTS_DIR = DATA_DIR / "plots"

# Local scratch directory for debug dumps and experiments
SCRATCH_DIR = PROJECT_ROOT / "scratch"

# ------------------------
# League Configs
# ------------------------
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
