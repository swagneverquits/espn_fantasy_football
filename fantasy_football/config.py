"""Explicit loading of user-selected leagues from TOML."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

from fantasy_football.constants import LEAGUE_CONFIG_PATH


@dataclass(frozen=True)
class LeagueConfig:
    espn: dict[str, str]
    sleeper: dict[str, str]
    path: Path = LEAGUE_CONFIG_PATH

    def league_id(self, provider: str, name: str) -> str:
        leagues = self.espn if provider == "espn" else self.sleeper
        if name not in leagues:
            raise ValueError(
                f"Unknown {provider} league '{name}'. Expected one of: {', '.join(leagues)}"
            )
        return leagues[name]


def load_leagues(path: str | Path = LEAGUE_CONFIG_PATH) -> LeagueConfig:
    path = Path(path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Create {path} from leagues.toml.example")
    with path.open("rb") as file:
        data = tomllib.load(file)
    providers = {}
    for provider in ("espn", "sleeper"):
        values = data.get(provider, {})
        if not isinstance(values, dict):
            raise ValueError(f"[{provider}] must contain league names and IDs")
        if any(
            isinstance(value, bool) or not str(value).isdigit()
            for value in values.values()
        ):
            raise ValueError(f"[{provider}] league IDs must be numeric")
        providers[provider] = {name: str(value) for name, value in values.items()}
    if not any(providers.values()):
        raise ValueError("Configure at least one league in [espn] or [sleeper]")
    return LeagueConfig(**providers, path=path)
