"""Command-line interface for scraping and analyzing fantasy football data."""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from fantasy_football.analysis.plotting import generate_matchup_plots
from fantasy_football.config import ESPN_LEAGUES, SLEEPER_LEAGUES
from fantasy_football.constants import (
    DEFAULT_INTERVAL_SECONDS,
    DEFAULT_RETRY_SECONDS,
    PARQUET_DIR,
)
from fantasy_football.scrapers.espn.scraper import main as run_espn
from fantasy_football.scrapers.sleeper.scraper import main as run_sleeper
from fantasy_football.storage.sync import PARQUET_TABLES, sync_parquet_prefix

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _add_polling_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_SECONDS)
    parser.add_argument("--retry-interval", type=int, default=DEFAULT_RETRY_SECONDS)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--no-schedule-gate", action="store_true")
    parser.add_argument("--storage", choices=("local", "gcs"), default="local")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fantasy football scraping tools.")
    commands = parser.add_subparsers(dest="command", required=True)
    scrape = commands.add_parser("scrape", help="Collect live league snapshots.")
    providers = scrape.add_subparsers(dest="provider", required=True)
    espn = providers.add_parser("espn", help="Scrape one configured ESPN league.")
    espn.add_argument("--league", choices=sorted(ESPN_LEAGUES), required=True)
    _add_polling_args(espn)
    sleeper = providers.add_parser("sleeper", help="Scrape one Sleeper league.")
    sleeper.add_argument("--league-id", required=True)
    _add_polling_args(sleeper)
    all_leagues = providers.add_parser(
        "all", help="Scrape all configured leagues in parallel."
    )
    _add_polling_args(all_leagues)
    analyze = commands.add_parser(
        "analyze", help="Generate matchup plots from local DuckDB/Parquet data."
    )
    analyze.add_argument("--season", type=int, required=True)
    analyze.add_argument("--week", type=int, required=True)
    analyze.add_argument("--league", required=True)
    analyze.add_argument("--provider", choices=("espn", "sleeper"), default="espn")
    sync = commands.add_parser("sync", help="Download one league/week from GCS.")
    sync.add_argument("--bucket", required=True)
    sync.add_argument("--provider", choices=("espn", "sleeper"), required=True)
    sync.add_argument("--league-id", required=True)
    sync.add_argument("--season", type=int, required=True)
    sync.add_argument("--week", type=int, required=True)
    sync.add_argument("--output-dir", type=Path, default=PARQUET_DIR)
    sync.add_argument("--tables", nargs="+", choices=PARQUET_TABLES)

    return parser


def _polling_args(args: argparse.Namespace) -> dict[str, object]:
    return {
        "season": args.season,
        "interval_seconds": args.interval,
        "retry_seconds": args.retry_interval,
        "once": args.once,
        "schedule_gate": not args.no_schedule_gate,
        "storage_mode": args.storage,
    }


def _run_all(args: argparse.Namespace) -> int:
    common = [
        "--season",
        str(args.season),
        "--interval",
        str(args.interval),
        "--retry-interval",
        str(args.retry_interval),
        "--storage",
        args.storage,
    ]
    if args.once:
        common.append("--once")
    if args.no_schedule_gate:
        common.append("--no-schedule-gate")
    commands = []
    for league in ESPN_LEAGUES:
        commands.append(
            [
                sys.executable,
                "-m",
                "fantasy_football.cli",
                "scrape",
                "espn",
                "--league",
                league,
                *common,
            ]
        )
    for league_id in SLEEPER_LEAGUES.values():
        commands.append(
            [
                sys.executable,
                "-m",
                "fantasy_football.cli",
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
        args.interval,
        not args.no_schedule_gate,
        args.storage,
    )
    bucket = os.getenv("GCS_BUCKET")
    if bucket and args.storage == "gcs":
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
                    if status is not None
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


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler()],
    )
    args = build_parser().parse_args(argv)
    if args.command == "scrape" and args.provider == "espn":
        run_espn(league=args.league, **_polling_args(args))
    elif args.command == "scrape" and args.provider == "sleeper":
        run_sleeper(league_id=args.league_id, **_polling_args(args))
    elif args.command == "scrape" and args.provider == "all":
        return _run_all(args)
    elif args.command == "sync":
        count = sync_parquet_prefix(
            args.bucket,
            provider=args.provider,
            league_id=args.league_id,
            season=args.season,
            matchup_period=args.week,
            output_dir=args.output_dir,
            tables=args.tables,
        )
        logging.info("Downloaded %d new Parquet objects", count)
    else:
        for path in generate_matchup_plots(
            args.season, args.week, args.league, args.provider
        ):
            print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
