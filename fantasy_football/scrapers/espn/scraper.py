"""ESPN Fantasy Football scraper."""

from fantasy_football.config import LEAGUE_IDS
from fantasy_football.io import get_results_file
from fantasy_football.storage import write_snapshot, write_sqlite_snapshot

from .client import fetch_league_data
from .parser import current_week, matchup_rows
from ..base import Scraper


class ESPNScraper(Scraper):
    provider = "ESPN"

    def __init__(self, league: str, *, season: int = 2026):
        if league not in LEAGUE_IDS:
            raise ValueError(f"Unknown league '{league}'")
        self.league = league
        self.league_id = LEAGUE_IDS[league]
        self.season = season

    def scrape_once(self) -> int:
        data = fetch_league_data(self.season, self.league_id)
        week = current_week(data)
        path = get_results_file(self.season, week, self.league)
        path.parent.mkdir(parents=True, exist_ok=True)
        frame = matchup_rows(data, matchup_period=week)
        rows = write_snapshot(path, frame)
        write_sqlite_snapshot(
            frame,
            provider="espn",
            league_id=self.league_id,
            season=self.season,
            matchup_period=week,
            data=data,
        )
        return rows


def main(
    league: str,
    *,
    season: int = 2026,
    interval_seconds=30,
    retry_seconds=30,
    once=False,
):
    return ESPNScraper(league, season=season).run(
        interval_seconds=interval_seconds,
        retry_seconds=retry_seconds,
        once=once,
    )