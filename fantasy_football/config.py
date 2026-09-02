"""Load user-selected league configuration from TOML."""

import tomllib

from fantasy_football.constants import LEAGUE_CONFIG_PATH


def _load_leagues() -> dict:
    if not LEAGUE_CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Create {LEAGUE_CONFIG_PATH} from leagues.toml.example"
        )
    with LEAGUE_CONFIG_PATH.open("rb") as file:
        config = tomllib.load(file)
    if not config.get("espn") and not config.get("sleeper"):
        raise ValueError("Configure at least one league in [espn] or [sleeper]")
    return config


_LEAGUES = _load_leagues()
ESPN_LEAGUES = {
    name: str(league_id) for name, league_id in _LEAGUES.get("espn", {}).items()
}

LEAGUE_IDS = {name: int(league_id) for name, league_id in ESPN_LEAGUES.items()}

SLEEPER_LEAGUES = {
    name: str(league_id) for name, league_id in _LEAGUES.get("sleeper", {}).items()
}
