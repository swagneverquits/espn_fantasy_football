"""Polling, schedule gating, retries, and supervision of league workers."""

import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fantasy_football.config import LeagueConfig
from fantasy_football.constants import (
    DEFAULT_INTERVAL_SECONDS,
    DEFAULT_PREGAME_BUFFER_SECONDS,
    DEFAULT_RETRY_SECONDS,
    DEFAULT_SCHEDULE_REFRESH_SECONDS,
    DEFAULT_SEASON,
    PROJECT_ROOT,
)
from fantasy_football.scrapers.base import Scraper
from fantasy_football.scrapers.schedule.cache import get_game_starts
from fantasy_football.scrapers.schedule.windows import (
    active_window,
    build_game_windows,
    seconds_until_next_window,
)
from fantasy_football.storage.pipeline import ParquetSnapshotWriter

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunOptions:
    season: int = DEFAULT_SEASON
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS
    retry_seconds: int = DEFAULT_RETRY_SECONDS
    once: bool = False
    schedule_gate: bool = True
    storage_mode: str = "local"


class Poller:
    """Run a provider using an injected snapshot writer."""

    def __init__(self, scraper: Scraper, writer: ParquetSnapshotWriter):
        self.scraper = scraper
        self.writer = writer

    @property
    def log_name(self) -> str:
        return self.scraper.log_name

    def scrape_once(self) -> int:
        return self.writer.write(self.scraper.fetch_snapshot())

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


def run_all(leagues: LeagueConfig, options: RunOptions) -> int:
    common = [
        "--season",
        str(options.season),
        "--interval",
        str(options.interval_seconds),
        "--retry-interval",
        str(options.retry_seconds),
        "--storage",
        options.storage_mode,
    ]
    if options.once:
        common.append("--once")
    if not options.schedule_gate:
        common.append("--no-schedule-gate")
    commands = []
    for league in leagues.espn:
        commands.append(
            [
                sys.executable,
                "-m",
                "fantasy_football.cli",
                "--config",
                str(leagues.path),
                "scrape",
                "espn",
                "--league",
                league,
                *common,
            ]
        )
    for league_id in leagues.sleeper.values():
        commands.append(
            [
                sys.executable,
                "-m",
                "fantasy_football.cli",
                "--config",
                str(leagues.path),
                "scrape",
                "sleeper",
                "--league-id",
                league_id,
                *common,
            ]
        )
    logging.info(
        "Starting %d league workers: interval=%ss schedule_gate=%s storage=%s",
        len(commands),
        options.interval_seconds,
        options.schedule_gate,
        options.storage_mode,
    )
    bucket = os.getenv("GCS_BUCKET")
    if bucket and options.storage_mode == "gcs":
        logging.info("Snapshot destination: GCS bucket=%s", bucket)

    worker_env = os.environ.copy()
    worker_env["FANTASY_FOOTBALL_WORKER"] = "1"
    processes = [
        subprocess.Popen(command, cwd=PROJECT_ROOT, env=worker_env)
        for command in commands
    ]
    try:
        while True:
            statuses = [process.poll() for process in processes]
            if all(status is not None for status in statuses):
                return max(statuses, default=0)
            exited = next(
                (
                    (index, status)
                    for index, status in enumerate(statuses)
                    if status is not None and (not options.once or status != 0)
                ),
                None,
            )
            if exited is not None:
                index, status = exited
                logging.error(
                    "League worker %d exited unexpectedly with status %d; stopping remaining workers",
                    index + 1,
                    status,
                )
                for process in processes:
                    if process.poll() is None:
                        process.terminate()
                for process in processes:
                    process.wait()
                return status or 1
            time.sleep(1)
    except KeyboardInterrupt:
        for process in processes:
            process.terminate()
        for process in processes:
            process.wait()
        return 130
