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
    raise ValueError("❌ ESPN_EMAIL and ESPN_PASSWORD must be set in environment variables or .env")


# ------------------------
# Paths
# ------------------------

# Path to ChromeDriver binary
DRIVER_PATH = os.getenv("CHROMEDRIVER_PATH", "/usr/local/bin/chromedriver")

# Project root = the repo root, one level above this file’s parent
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Data directory always under /data
DATA_DIR = PROJECT_ROOT / "data"

# Results directory
RESULTS_DIR = DATA_DIR / "results"

# Plots directory
PLOTS_DIR = DATA_DIR / "plots"


# ------------------------
# League Configs
# ------------------------
LEAGUE_IDS = [
    1850396491,  # college peeps
    1012938436,  # high school boyos
]
