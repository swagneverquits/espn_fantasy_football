"""Project-wide constants for external services and runtime defaults."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_INTERVAL_SECONDS = 30
DEFAULT_RETRY_SECONDS = 30
RESULTS_DIR = PROJECT_ROOT / "results" / "data"
PLOTS_DIR = PROJECT_ROOT / "results" / "plots"
SQLITE_PATH = RESULTS_DIR / "fantasy_football.sqlite"

ESPN_API_HOST = "https://lm-api-reads.fantasy.espn.com"
SLEEPER_API_HOST = "https://api.sleeper.app/v1"
SLEEPER_DATA_HOST = "https://api.sleeper.com"
PROVIDER_COL = "provider"
LEAGUE_ID_COL = "league_id"
SEASON_COL = "season"
MATCHUP_PERIOD_COL = "matchup_period"
MATCHUP_ID_COL = "matchup_id"
TIMESTAMP_COL = "timestamp"
TEAM_ID_COL = "team_id"

COMMON_INDEX_COLS = (
    PROVIDER_COL,
    LEAGUE_ID_COL,
    SEASON_COL,
)
TEAM_SNAPSHOTS_TABLE = "team_snapshots"
PLAYER_SNAPSHOTS_TABLE = "player_snapshots"
TEAM_METADATA_TABLE = "team_metadata"
LEAGUE_METADATA_TABLE = "league_metadata"
PLAYER_METADATA_TABLE = "player_metadata"
LEAGUE_CONFIG_PATH = PROJECT_ROOT / "config" / "leagues.toml"
