"""Shared interface and polling loop for fantasy football scrapers."""

from abc import ABC, abstractmethod
import logging
import time

from fantasy_football.storage import DEFAULT_INTERVAL_SECONDS, DEFAULT_RETRY_SECONDS


class Scraper(ABC):
    """Common polling interface implemented by each provider scraper."""

    provider = "unknown"

    @abstractmethod
    def scrape_once(self) -> int:
        """Fetch and persist one snapshot, returning the row count."""

    def run(
        self,
        *,
        interval_seconds=DEFAULT_INTERVAL_SECONDS,
        retry_seconds=DEFAULT_RETRY_SECONDS,
        once=False,
    ):
        """Poll until stopped, retrying transient failures."""
        while True:
            try:
                rows = self.scrape_once()
                if once:
                    return rows
                time.sleep(interval_seconds)
            except Exception:
                logging.exception("%s scrape failed", self.provider)
                if once:
                    raise
                time.sleep(retry_seconds)