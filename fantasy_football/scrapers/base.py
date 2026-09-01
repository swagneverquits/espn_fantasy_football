"""Shared interface and polling loop for fantasy football scrapers."""

import logging
import time
from abc import ABC, abstractmethod
from typing import Any

import pandas as pd

from fantasy_football.constants import DEFAULT_INTERVAL_SECONDS, DEFAULT_RETRY_SECONDS

JSONData = dict[str, Any]


class Scraper(ABC):
    """Common lifecycle for provider-specific fantasy football scrapers."""

    provider = "unknown"

    @abstractmethod
    def get_league_metadata(self) -> JSONData:
        """Return league-level metadata needed by this provider."""

    @abstractmethod
    def get_team_metadata(self, league_metadata: JSONData) -> Any:
        """Return the current team/roster metadata."""

    @abstractmethod
    def get_player_metadata(self, league_metadata: JSONData, team_metadata: Any) -> Any:
        """Return player metadata needed to normalize the snapshot."""

    @abstractmethod
    def get_live_snapshot(
        self,
        league_metadata: JSONData,
        team_metadata: Any,
        player_metadata: Any,
    ) -> JSONData:
        """Fetch the live matchup and projection data."""

    @abstractmethod
    def normalize_snapshot(
        self,
        league_metadata: JSONData,
        team_metadata: Any,
        player_metadata: Any,
        live_snapshot: JSONData,
    ) -> pd.DataFrame:
        """Convert provider data into the common snapshot DataFrame."""

    @abstractmethod
    def persist_snapshot(
        self,
        league_metadata: JSONData,
        team_metadata: Any,
        player_metadata: Any,
        live_snapshot: JSONData,
        frame: pd.DataFrame,
    ) -> int:
        """Persist one normalized snapshot, returning its row count."""

    def scrape_once(self) -> int:
        league_metadata = self.get_league_metadata()
        team_metadata = self.get_team_metadata(league_metadata)
        player_metadata = self.get_player_metadata(league_metadata, team_metadata)
        live_snapshot = self.get_live_snapshot(
            league_metadata, team_metadata, player_metadata
        )
        frame = self.normalize_snapshot(
            league_metadata, team_metadata, player_metadata, live_snapshot
        )
        return self.persist_snapshot(
            league_metadata,
            team_metadata,
            player_metadata,
            live_snapshot,
            frame,
        )

    def run(
        self,
        *,
        interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
        retry_seconds: int = DEFAULT_RETRY_SECONDS,
        once: bool = False,
    ) -> int | None:
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
