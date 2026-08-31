"""Read-only client for the Sleeper fantasy football API."""

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_HOST = "https://api.sleeper.app/v1"


class SleeperAPIError(RuntimeError):
    """Raised when Sleeper returns an unusable response."""


def fetch_json(path: str, *, timeout: int = 30):
    try:
        with urlopen(
            Request(
                f"{API_HOST}{path}",
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


def fetch_league_data(league_id: str):
    """Fetch league metadata, users, rosters, and the current NFL week."""
    league = fetch_json(f"/league/{league_id}")
    users = fetch_json(f"/league/{league_id}/users")
    rosters = fetch_json(f"/league/{league_id}/rosters")
    state = fetch_json("/state/nfl")
    week = int(state["week"])
    matchups = fetch_json(f"/league/{league_id}/matchups/{week}")
    return {
        "league": league,
        "users": users,
        "rosters": rosters,
        "matchups": matchups,
        "week": week,
    }
