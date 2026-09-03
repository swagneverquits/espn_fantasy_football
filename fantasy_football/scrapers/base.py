"""Shared interface and polling loop for fantasy football scrapers."""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from fantasy_football.constants import (
    DEFAULT_INTERVAL_SECONDS,
    DEFAULT_RETRY_SECONDS,
    DEFAULT_SCHEDULE_REFRESH_SECONDS,
)
from fantasy_football.schedule import (
    active_window,
    build_game_windows,
    fetch_nfl_game_starts,
    seconds_until_next_window,
)

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
        schedule_gate: bool = True,
        schedule_refresh_seconds: int = DEFAULT_SCHEDULE_REFRESH_SECONDS,
    ) -> int | None:
        """Poll during merged NFL game windows, retrying transient failures."""
        if once or not schedule_gate:
            return self._run_without_schedule(
                interval_seconds=interval_seconds,
                retry_seconds=retry_seconds,
                once=once,
            )

        windows = ()
        next_schedule_refresh = datetime.min.replace(tzinfo=timezone.utc)
        while True:
            try:
                now = datetime.now(timezone.utc)
                if now >= next_schedule_refresh:
                    windows = build_game_windows(fetch_nfl_game_starts(now))
                    next_schedule_refresh = (
                        now
                        + pd.Timedelta(
                            seconds=schedule_refresh_seconds
                        ).to_pytimedelta()
                    )
                    logging.info(
                        "Schedule gate refreshed: %d polling window(s)", len(windows)
                    )
                if active_window(windows, now) is None:
                    delay = seconds_until_next_window(windows, now)
                    sleep_seconds = min(
                        schedule_refresh_seconds,
                        delay if delay is not None else schedule_refresh_seconds,
                    )
                    time.sleep(max(1.0, sleep_seconds))
                    continue
                self.scrape_once()
                time.sleep(interval_seconds)
            except Exception:
                logging.exception("%s scrape failed", self.provider)
                time.sleep(retry_seconds)

    def _run_without_schedule(
        self,
        *,
        interval_seconds: int,
        retry_seconds: int,
        once: bool,
    ) -> int | None:
        """Run immediate polling, used by one-shot and ungated runs."""
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
