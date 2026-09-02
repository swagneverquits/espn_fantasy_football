"""ESPN Fantasy Football scraper."""

import pandas as pd

from fantasy_football.config import LEAGUE_IDS
from fantasy_football.parquet_pipeline import configured_writer

from ..base import JSONData, Scraper
from .client import fetch_league_data
from .parser import current_week, matchup_rows


class ESPNScraper(Scraper):
    provider = "ESPN"

    def __init__(self, league: str, *, season: int = 2026):
        if league not in LEAGUE_IDS:
            raise ValueError(f"Unknown league '{league}'")
        self.league = league
        self.league_id = LEAGUE_IDS[league]
        self.season = season
        self.snapshot_writer = configured_writer()

    def get_league_metadata(self) -> JSONData:
        """Fetch ESPN's combined league payload."""
        return fetch_league_data(self.season, self.league_id)

    def get_team_metadata(self, league_metadata: JSONData) -> JSONData:
        return league_metadata

    def get_player_metadata(
        self, league_metadata: JSONData, team_metadata: JSONData
    ) -> JSONData:
        return league_metadata

    def get_live_snapshot(
        self,
        league_metadata: JSONData,
        team_metadata: JSONData,
        player_metadata: JSONData,
    ) -> JSONData:
        return league_metadata

    def normalize_snapshot(
        self,
        league_metadata: JSONData,
        team_metadata: JSONData,
        player_metadata: JSONData,
        live_snapshot: JSONData,
    ) -> pd.DataFrame:
        week = current_week(live_snapshot)
        return matchup_rows(live_snapshot, matchup_period=week)

    def persist_snapshot(
        self,
        league_metadata: JSONData,
        team_metadata: JSONData,
        player_metadata: JSONData,
        live_snapshot: JSONData,
        frame: pd.DataFrame,
    ) -> int:
        week = current_week(live_snapshot)
        rows = len(frame)
        if not rows:
            return 0
        self.snapshot_writer.write(
            frame,
            provider="espn",
            league_id=self.league_id,
            season=self.season,
            matchup_period=week,
            data=live_snapshot,
        )
        return rows


def main(
    league: str,
    *,
    season: int = 2026,
    interval_seconds: int = 30,
    retry_seconds: int = 30,
    once: bool = False,
):
    return ESPNScraper(league, season=season).run(
        interval_seconds=interval_seconds,
        retry_seconds=retry_seconds,
        once=once,
    )
