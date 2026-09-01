"""Sleeper fantasy football scraper."""

from fantasy_football.io import get_results_file
from fantasy_football.storage import write_snapshot, write_sqlite_snapshot

from .client import fetch_league_data
from .parser import matchup_rows
from ..base import Scraper


class SleeperScraper(Scraper):
    provider = "Sleeper"

    def __init__(self, league_id: str, *, season: int = 2026):
        self.league_id = str(league_id)
        self.season = season

    def scrape_once(self) -> int:
        data = fetch_league_data(self.league_id)
        week = data["week"]
        path = get_results_file(self.season, week, f"sleeper_{self.league_id}")
        path.parent.mkdir(parents=True, exist_ok=True)
        frame = matchup_rows(data, matchup_period=week)
        rows = write_snapshot(path, frame)
        write_sqlite_snapshot(
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
    interval_seconds=30,
    retry_seconds=30,
    once=False,
):
    return SleeperScraper(league_id, season=season).run(
        interval_seconds=interval_seconds,
        retry_seconds=retry_seconds,
        once=once,
    )