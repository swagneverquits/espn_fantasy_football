"""Command-line interface for scraping and analyzing fantasy football data."""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from fantasy_football.analysis.plotting import generate_matchup_plots
from fantasy_football.config import ESPN_LEAGUES, SLEEPER_LEAGUES
from fantasy_football.compaction import compact_gcs_week
from fantasy_football.constants import (
    DEFAULT_INTERVAL_SECONDS,
    DEFAULT_RETRY_SECONDS,
    PARQUET_DIR,
)
from fantasy_football.scrapers.espn.scraper import main as run_espn
from fantasy_football.scrapers.sleeper.scraper import main as run_sleeper
from fantasy_football.sync import sync_parquet_prefix

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _add_polling_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_SECONDS)
    parser.add_argument("--retry-interval", type=int, default=DEFAULT_RETRY_SECONDS)
    parser.add_argument("--once", action="store_true")


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
        "analyze", help="Generate matchup plots from local Parquet data."
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
    compact = commands.add_parser(
        "compact", help="Compact one GCS league/week into Parquet objects."
    )
    compact.add_argument("--bucket", required=True)
    compact.add_argument("--provider", choices=("espn", "sleeper"), required=True)
    compact.add_argument("--league-id", required=True)
    compact.add_argument("--season", type=int, required=True)
    compact.add_argument("--week", type=int, required=True)

    return parser


def _polling_args(args: argparse.Namespace) -> dict[str, object]:
    return {
        "season": args.season,
        "interval_seconds": args.interval,
        "retry_seconds": args.retry_interval,
        "once": args.once,
    }


def _run_all(args: argparse.Namespace) -> int:
    common = [
        "--season",
        str(args.season),
        "--interval",
        str(args.interval),
        "--retry-interval",
        str(args.retry_interval),
    ]
    if args.once:
        common.append("--once")
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
    processes = [subprocess.Popen(command, cwd=PROJECT_ROOT) for command in commands]
    try:
        return max(process.wait() for process in processes)
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
        )
        logging.info("Downloaded %d Parquet objects", count)
    elif args.command == "compact":
        outputs = compact_gcs_week(
            args.bucket,
            provider=args.provider,
            league_id=args.league_id,
            season=args.season,
            matchup_period=args.week,
        )
        logging.info("Wrote %d compacted Parquet objects", len(outputs))
    else:
        for path in generate_matchup_plots(
            args.season, args.week, args.league, args.provider
        ):
            print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
