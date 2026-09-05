"""ESPN snapshot acquisition."""

from fantasy_football.constants import DEFAULT_SEASON
from fantasy_football.snapshot import Snapshot

from ..base import Scraper
from .client import fetch_league_data
from .parser import parse_snapshot


class ESPNScraper(Scraper):
    provider = "espn"

    def __init__(self, league_id: str | int, *, season: int = DEFAULT_SEASON):
        self.league_id = str(league_id)
        self.season = season

    def fetch_snapshot(self) -> Snapshot:
        data = fetch_league_data(self.season, int(self.league_id))
        return parse_snapshot(data, league_id=self.league_id, season=self.season)
