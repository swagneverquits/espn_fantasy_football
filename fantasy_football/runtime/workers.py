"""Configuration and supervision of league worker processes."""

import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass

from fantasy_football.config import LeagueConfig
from fantasy_football.constants import (
    DEFAULT_INTERVAL_SECONDS,
    DEFAULT_RETRY_SECONDS,
    DEFAULT_SEASON,
    PROJECT_ROOT,
)


@dataclass(frozen=True)
class RunOptions:
    season: int = DEFAULT_SEASON
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS
    retry_seconds: int = DEFAULT_RETRY_SECONDS
    once: bool = False
    schedule_gate: bool = True
    storage_mode: str = "local"


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
