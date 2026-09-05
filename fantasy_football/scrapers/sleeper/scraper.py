"""Sleeper fantasy football scraper."""

from typing import Any

import pandas as pd

from fantasy_football.storage.pipeline import configured_writer

from ..base import JSONData, Scraper
from .client import fetch_json, fetch_weekly_player_data
from .parser import matchup_rows


class SleeperScraper(Scraper):
    provider = "Sleeper"

    def __init__(
        self, league_id: str, *, season: int = 2026, storage_mode: str = "local"
    ):
        self.league_id = str(league_id)
        self.season = season
        self._weekly_metadata: JSONData | None = None
        self.snapshot_writer = configured_writer(storage_mode)

    def get_league_metadata(self) -> JSONData:
        """Fetch league identity and users once for this scraper run."""
        if self._weekly_metadata is None:
            league = fetch_json(f"/league/{self.league_id}")
            users = fetch_json(f"/league/{self.league_id}/users")
            state = fetch_json("/state/nfl")
            self._weekly_metadata = {
                "league": league,
                "users": users,
                "week": int(state["week"]),
            }
        return self._weekly_metadata

    def get_team_metadata(self, league_metadata: JSONData) -> list[dict[str, Any]]:
        """Fetch rosters every poll so lineup changes are captured."""
        return fetch_json(f"/league/{self.league_id}/rosters")

    def get_player_metadata(
        self, league_metadata: JSONData, team_metadata: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        # Sleeper player identity is carried by the live roster response.
        return team_metadata

    def get_live_snapshot(
        self,
        league_metadata: JSONData,
        team_metadata: list[dict[str, Any]],
        player_metadata: list[dict[str, Any]],
    ) -> JSONData:
        week = league_metadata["week"]
        league = league_metadata["league"]
        matchups = fetch_json(f"/league/{self.league_id}/matchups/{week}")
        player_data = fetch_weekly_player_data(
            league["sport"], int(league["season"]), week
        )
        return {"matchups": matchups, "player_data": player_data}

    def normalize_snapshot(
        self,
        league_metadata: JSONData,
        team_metadata: list[dict[str, Any]],
        player_metadata: list[dict[str, Any]],
        live_snapshot: JSONData,
    ) -> pd.DataFrame:
        data = {**league_metadata, "rosters": team_metadata, **live_snapshot}
        return matchup_rows(data, matchup_period=data["week"])

    def persist_snapshot(
        self,
        league_metadata: JSONData,
        team_metadata: list[dict[str, Any]],
        player_metadata: list[dict[str, Any]],
        live_snapshot: JSONData,
        frame: pd.DataFrame,
    ) -> int:
        data = {**league_metadata, "rosters": team_metadata, **live_snapshot}
        week = data["week"]
        rows = len(frame)
        if not rows:
            return 0
        self.snapshot_writer.write(
            frame,
            provider="sleeper",
            league_id=self.league_id,
            season=self.season,
            matchup_period=week,
            data=data,
        )
        return rows


def main(
    league_id: str,
    *,
    season: int = 2026,
    interval_seconds: int = 30,
    retry_seconds: int = 30,
    once: bool = False,
    schedule_gate: bool = True,
    storage_mode: str = "local",
):
    return SleeperScraper(league_id, season=season, storage_mode=storage_mode).run(
        interval_seconds=interval_seconds,
        retry_seconds=retry_seconds,
        once=once,
        schedule_gate=schedule_gate,
    )
