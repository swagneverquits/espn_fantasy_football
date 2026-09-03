"""Project-wide constants for external services and runtime defaults."""

from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
LEAGUE_CONFIG_PATH = PROJECT_ROOT / "config" / "leagues.toml"
PARQUET_DIR = PROJECT_ROOT / "results" / "parquet"
PLOTS_DIR = PROJECT_ROOT / "results" / "plots"

# Runtime defaults
DEFAULT_INTERVAL_SECONDS = 30
DEFAULT_RETRY_SECONDS = 30
DEFAULT_SCHEDULE_REFRESH_SECONDS = 2 * 60 * 60
DEFAULT_PREGAME_BUFFER_SECONDS = 15 * 60
DEFAULT_GAME_WINDOW_SECONDS = 4 * 60 * 60

# External service endpoints
ESPN_API_HOST = "https://lm-api-reads.fantasy.espn.com"
SLEEPER_API_HOST = "https://api.sleeper.app/v1"
SLEEPER_DATA_HOST = "https://api.sleeper.com"

# Shared schema columns
PROVIDER_COL = "provider"
LEAGUE_ID_COL = "league_id"
SEASON_COL = "season"
MATCHUP_PERIOD_COL = "matchup_period"
MATCHUP_ID_COL = "matchup_id"
TIMESTAMP_COL = "timestamp"
TEAM_ID_COL = "team_id"
COMMON_INDEX_COLS = (PROVIDER_COL, LEAGUE_ID_COL, SEASON_COL)
