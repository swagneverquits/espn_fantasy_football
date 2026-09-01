"""Read-only client for the Sleeper fantasy football API."""

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fantasy_football.constants import SLEEPER_API_HOST, SLEEPER_DATA_HOST


class SleeperAPIError(RuntimeError):
    """Raised when Sleeper returns an unusable response."""


def fetch_json(path: str, *, timeout: int = 30):
    try:
        with urlopen(
            Request(
                f"{SLEEPER_API_HOST}{path}",
                headers={"User-Agent": "Fantasy Football collector"},
            ),
            timeout=timeout,
        ) as response:
            return json.load(response)
    except HTTPError as exc:
        raise SleeperAPIError(f"Sleeper API returned HTTP {exc.code}") from exc
    except URLError as exc:
        raise SleeperAPIError(f"Could not reach Sleeper API: {exc.reason}") from exc
    except ValueError as exc:
        raise SleeperAPIError("Sleeper API returned invalid JSON") from exc


def fetch_data_json(path: str, *, timeout: int = 30):
    """Fetch player stats/projections from Sleeper's data API."""
    try:
        with urlopen(
            Request(
                f"{SLEEPER_DATA_HOST}{path}",
                headers={"User-Agent": "Fantasy Football collector"},
            ),
            timeout=timeout,
        ) as response:
            return json.load(response)
    except HTTPError as exc:
        raise SleeperAPIError(f"Sleeper data API returned HTTP {exc.code}") from exc
    except URLError as exc:
        raise SleeperAPIError(
            f"Could not reach Sleeper data API: {exc.reason}"
        ) from exc
    except ValueError as exc:
        raise SleeperAPIError("Sleeper data API returned invalid JSON") from exc


def fetch_weekly_player_data(sport: str, season: int, week: int):
    """Fetch the raw weekly stats and projections used by the web app."""
    suffix = f"/{sport}/{season}/{week}?season_type=regular"
    return {
        "stats": fetch_data_json(f"/stats{suffix}"),
        "projections": fetch_data_json(f"/projections{suffix}"),
    }
