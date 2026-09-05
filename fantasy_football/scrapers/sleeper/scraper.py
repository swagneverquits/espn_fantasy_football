"""Fetch SLEEPER API data and produce normalized snapshots."""

import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fantasy_football.constants import (
    DEFAULT_SCHEDULE_REFRESH_SECONDS,
    DEFAULT_SEASON,
    SLEEPER_API_HOST,
    SLEEPER_DATA_HOST,
)
from fantasy_football.snapshot import Snapshot

from ..base import JSONData, Scraper
from .parser import parse_snapshot


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


class SleeperScraper(Scraper):
    provider = "sleeper"

    def __init__(self, league_id: str | int, *, season: int = DEFAULT_SEASON):
        self.league_id = str(league_id)
        self.season = season
        self._weekly_metadata: JSONData | None = None
        self._next_metadata_refresh = 0.0

    def get_league_metadata(self) -> JSONData:
        """Check NFL state periodically and refresh identity when the week changes."""
        now = time.monotonic()
        if self._weekly_metadata is None or now >= self._next_metadata_refresh:
            state = fetch_json("/state/nfl")
            week = int(state["week"])
            if (
                self._weekly_metadata is not None
                and self._weekly_metadata["week"] == week
            ):
                self._next_metadata_refresh = now + DEFAULT_SCHEDULE_REFRESH_SECONDS
                return self._weekly_metadata
            league = fetch_json(f"/league/{self.league_id}")
            users = fetch_json(f"/league/{self.league_id}/users")
            self._weekly_metadata = {
                "league": league,
                "users": users,
                "week": week,
            }
            self._next_metadata_refresh = now + DEFAULT_SCHEDULE_REFRESH_SECONDS
        return self._weekly_metadata

    def fetch_snapshot(self) -> Snapshot:
        metadata = self.get_league_metadata()
        week, league = metadata["week"], metadata["league"]
        data = {
            **metadata,
            "rosters": fetch_json(f"/league/{self.league_id}/rosters"),
            "matchups": fetch_json(f"/league/{self.league_id}/matchups/{week}"),
            "player_data": fetch_weekly_player_data(
                league["sport"], int(league["season"]), week
            ),
        }
        return parse_snapshot(data, league_id=self.league_id, season=self.season)
