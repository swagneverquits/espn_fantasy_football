"""Per-league polling, schedule gating, and retries."""

import logging
import os
import time
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fantasy_football.constants import (
    DEFAULT_INTERVAL_SECONDS,
    DEFAULT_PREGAME_BUFFER_SECONDS,
    DEFAULT_RETRY_SECONDS,
    DEFAULT_SCHEDULE_REFRESH_SECONDS,
)
from fantasy_football.runtime.status import WorkerStatus
from fantasy_football.schedule.cache import get_game_starts
from fantasy_football.schedule.windows import (
    active_window,
    build_game_windows,
    seconds_until_next_window,
)
from fantasy_football.scrapers.base import Scraper
from fantasy_football.storage.writer import ParquetSnapshotWriter

logger = logging.getLogger(__name__)


class Poller:
    """Run a provider using an injected snapshot writer."""

    def __init__(
        self,
        scraper: Scraper,
        writer: ParquetSnapshotWriter,
        status: WorkerStatus | None = None,
    ):
        self.scraper = scraper
        self.writer = writer
        self.status = status
        self.errors = 0

    @property
    def log_name(self) -> str:
        return self.scraper.log_name

    def scrape_once(self) -> int:
        self._status(status="Scraping")
        try:
            rows = self.writer.write(self.scraper.fetch_snapshot())
        except Exception:
            self.errors += 1
            self._status(
                status="Retrying",
                last_result="Failed",
                last_scrape=time.time(),
                errors=self.errors,
            )
            raise
        now = time.time()
        self._status(
            status="Waiting", last_result="Success", last_scrape=now, last_success=now
        )
        return rows

    def _status(self, **changes: object) -> None:
        if self.status is not None:
            self.status.update(**changes)

    def run(
        self,
        *,
        interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
        retry_seconds: int = DEFAULT_RETRY_SECONDS,
        once: bool = False,
        schedule_gate: bool = True,
        schedule_refresh_seconds: int = DEFAULT_SCHEDULE_REFRESH_SECONDS,
    ) -> int | None:
        with self.status if self.status is not None else nullcontext():
            return self._run(
                interval_seconds=interval_seconds,
                retry_seconds=retry_seconds,
                once=once,
                schedule_gate=schedule_gate,
                schedule_refresh_seconds=schedule_refresh_seconds,
            )

    def _run(
        self,
        *,
        interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
        retry_seconds: int = DEFAULT_RETRY_SECONDS,
        once: bool = False,
        schedule_gate: bool = True,
        schedule_refresh_seconds: int = DEFAULT_SCHEDULE_REFRESH_SECONDS,
    ) -> int | None:
        """Poll during merged NFL game windows, retrying transient failures."""
        if os.getenv("FANTASY_FOOTBALL_WORKER") != "1":
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
                        "  # | NFL wk | games | opens (ET)          | closes (ET)",
                        *[
                            f" {index:2d} | {','.join(map(str, window.nfl_weeks)) or '-':7} | {window.game_count:5d} | {window.start.astimezone(eastern):%a %m/%d %I:%M %p} | {window.end.astimezone(eastern):%a %m/%d %I:%M %p}"
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
                    self._status(status="Idle")
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
                self._status(status="Retrying")
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
                self._status(status="Retrying")
                logger.exception(
                    "%s cycle failed; retrying in %ss",
                    self.log_name,
                    retry_seconds,
                )
                if once:
                    raise
                time.sleep(retry_seconds)
