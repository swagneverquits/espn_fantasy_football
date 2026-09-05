"""Minimal interface implemented by fantasy providers."""

from abc import ABC, abstractmethod
from typing import Any

from fantasy_football.snapshot import Snapshot

JSONData = dict[str, Any]


class Scraper(ABC):
    provider: str
    league_id: str
    season: int

    @property
    def log_name(self) -> str:
        return f"{self.provider} league={self.league_id}"

    @abstractmethod
    def fetch_snapshot(self) -> Snapshot:
        """Fetch provider data and return the five normalized tables."""
