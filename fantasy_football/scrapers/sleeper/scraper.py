"""Sleeper snapshot acquisition and weekly metadata caching."""

import time

from fantasy_football.constants import DEFAULT_SCHEDULE_REFRESH_SECONDS, DEFAULT_SEASON
from fantasy_football.snapshot import Snapshot

from ..base import JSONData, Scraper
from .client import fetch_json, fetch_weekly_player_data
from .parser import parse_snapshot


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
