"""Shared interface and polling loop for fantasy football scrapers."""

from __future__ import annotations

import logging
import os
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from fantasy_football.constants import (
    DEFAULT_INTERVAL_SECONDS,
    DEFAULT_PREGAME_BUFFER_SECONDS,
    DEFAULT_RETRY_SECONDS,
    DEFAULT_SCHEDULE_REFRESH_SECONDS,
)
from fantasy_football.scrapers.schedule.cache import get_game_starts
from fantasy_football.scrapers.schedule.windows import (
    active_window,
    build_game_windows,
    seconds_until_next_window,
)

JSONData = dict[str, Any]
logger = logging.getLogger(__name__)
WORKER_PROCESS = os.getenv("FANTASY_FOOTBALL_WORKER") == "1"


class Scraper(ABC):
    """Common lifecycle for provider-specific fantasy football scrapers."""

    provider = "unknown"

    @property
    def log_name(self) -> str:
        """Return a concise provider and league identifier for logs."""
        league_id = getattr(self, "league_id", "unknown")
        return f"{self.provider} league={league_id}"

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
        """Fetch, normalize, and persist one provider snapshot."""
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
        if not WORKER_PROCESS:
            logger.info(
                "%s starting: interval=%ss schedule_gate=%s",
                self.log_name,
                interval_seconds,
                schedule_gate and not once,
            )
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
                schedule_refreshed = False
                if now >= next_schedule_refresh:
                    game_starts, schedule_refreshed = get_game_starts(
                        now, refresh_seconds=schedule_refresh_seconds
                    )
                    windows = build_game_windows(game_starts)
                    next_schedule_refresh = now + timedelta(
                        seconds=schedule_refresh_seconds
                    )
                    eastern = ZoneInfo("America/New_York")
                    window_summary = [
                        "  # | opens (ET)          | closes (ET)",
                        *[
                            f" {index:2d} | {window.start.astimezone(eastern):%a %m/%d %I:%M %p} | {window.end.astimezone(eastern):%a %m/%d %I:%M %p}"
                            for index, window in enumerate(windows, start=1)
                        ],
                    ]
                if active_window(windows, now) is None:
                    delay = seconds_until_next_window(windows, now)
                    sleep_seconds = min(
                        schedule_refresh_seconds,
                        delay if delay is not None else schedule_refresh_seconds,
                    )
                    if delay is None:
                        if schedule_refreshed:
                            logger.info(
                                "NFL schedule: games=%d windows=%d; no upcoming games; sleeping %.0f seconds",
                                len(game_starts),
                                len(windows),
                                sleep_seconds,
                            )
                    else:
                        next_window = next(
                            window for window in windows if window.start > now
                        )
                        eastern = ZoneInfo("America/New_York")
                        kickoff = next_window.start + timedelta(
                            seconds=DEFAULT_PREGAME_BUFFER_SECONDS
                        )
                        if schedule_refreshed:
                            logger.info(
                                "NFL schedule | %d games | %d windows\n%s\nnext kickoff: %s ET | window opens: %s ET | sleeping: %.0f seconds",
                                len(game_starts),
                                len(windows),
                                "\n".join(window_summary),
                                kickoff.astimezone(eastern).strftime(
                                    "%Y-%m-%d %I:%M %p"
                                ),
                                next_window.start.astimezone(eastern).strftime(
                                    "%Y-%m-%d %I:%M %p"
                                ),
                                sleep_seconds,
                            )
                    time.sleep(max(1.0, sleep_seconds))
                    continue
                started = time.monotonic()
                rows = self.scrape_once()
                logger.info(
                    "%s snapshot saved: rows=%d elapsed=%.2fs",
                    self.log_name,
                    rows,
                    time.monotonic() - started,
                )
                time.sleep(interval_seconds)
            except Exception:
                logger.exception(
                    "%s cycle failed; retrying in %ss",
                    self.log_name,
                    retry_seconds,
                )
                time.sleep(retry_seconds)

    def _run_without_schedule(
        self,
        *,
        interval_seconds: int,
        retry_seconds: int,
        once: bool,
    ) -> int | None:
        """Run immediate polling, used by one-shot and ungated runs."""
        logger.info(
            "%s running without schedule gate: interval=%ss",
            self.log_name,
            interval_seconds,
        )
        while True:
            try:
                started = time.monotonic()
                rows = self.scrape_once()
                logger.info(
                    "%s snapshot saved: rows=%d elapsed=%.2fs",
                    self.log_name,
                    rows,
                    time.monotonic() - started,
                )
                if once:
                    return rows
                time.sleep(interval_seconds)
            except Exception:
                logger.exception(
                    "%s cycle failed; retrying in %ss",
                    self.log_name,
                    retry_seconds,
                )
                if once:
                    raise
                time.sleep(retry_seconds)
