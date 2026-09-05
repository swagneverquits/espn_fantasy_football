"""Command-line wiring; configuration and dependencies load only when needed."""

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from fantasy_football.config import load_leagues
from fantasy_football.constants import (
    DEFAULT_INTERVAL_SECONDS,
    DEFAULT_RETRY_SECONDS,
    DEFAULT_SEASON,
    LEAGUE_CONFIG_PATH,
    PARQUET_DIR,
    PARQUET_TABLES,
    PLOTS_DIR,
)


def _add_polling_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--season",
        type=int,
        default=DEFAULT_SEASON,
        help=f"NFL season to scrape (default: {DEFAULT_SEASON}).",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL_SECONDS,
        help="Seconds between live snapshots (default: %(default)s).",
    )
    parser.add_argument(
        "--retry-interval",
        type=int,
        default=DEFAULT_RETRY_SECONDS,
        help="Seconds to wait after a failed scrape (default: %(default)s).",
    )
    parser.add_argument(
        "--once", action="store_true", help="Run one snapshot and then exit."
    )
    parser.add_argument(
        "--no-schedule-gate",
        action="store_true",
        help="Ignore NFL game windows and poll continuously.",
    )
    parser.add_argument(
        "--storage",
        choices=("local", "gcs"),
        default="local",
        help="Storage destination: local Parquet or Google Cloud Storage (default: local).",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fantasy football scraping tools.")
    parser.add_argument(
        "--config",
        type=Path,
        default=LEAGUE_CONFIG_PATH,
        help="League TOML configuration path.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    scrape = commands.add_parser("scrape", help="Collect live league snapshots.")
    providers = scrape.add_subparsers(dest="provider", required=True)
    espn = providers.add_parser("espn", help="Scrape one configured ESPN league.")
    espn.add_argument("--league", required=True)
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


def _analyze(args: argparse.Namespace) -> None:
    from fantasy_football.plotting import generate_matchup_plots
    from fantasy_football.storage.duckdb import load_matchup_results

    leagues = load_leagues(args.config)
    league_id = leagues.league_id(args.provider, args.league)
    data = load_matchup_results(
        PARQUET_DIR,
        provider=args.provider,
        league_id=league_id,
        season=args.season,
        matchup_period=args.week,
    )
    output = PLOTS_DIR / str(args.season) / args.league / f"week_{args.week}"
    for path in generate_matchup_plots(
        data, week=args.week, output_dir=output, league_name=args.league
    ):
        print(path)


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
    )
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "scrape":
        from fantasy_football.runner import Poller, RunOptions, run_all
        from fantasy_football.storage.pipeline import configured_writer

        options = RunOptions(
            args.season,
            args.interval,
            args.retry_interval,
            args.once,
            not args.no_schedule_gate,
            args.storage,
        )
        if options.interval_seconds <= 0 or options.retry_seconds <= 0:
            parser.error("Polling and retry intervals must be positive")
        if args.provider == "all":
            return run_all(load_leagues(args.config), options)
        if args.provider == "espn":
            from fantasy_football.scrapers.espn.scraper import ESPNScraper

            league_id = load_leagues(args.config).league_id("espn", args.league)
            scraper = ESPNScraper(league_id, season=args.season)
        else:
            from fantasy_football.scrapers.sleeper.scraper import SleeperScraper

            scraper = SleeperScraper(args.league_id, season=args.season)
        Poller(scraper, configured_writer(args.storage)).run(
            interval_seconds=options.interval_seconds,
            retry_seconds=options.retry_seconds,
            once=options.once,
            schedule_gate=options.schedule_gate,
        )
    elif args.command == "sync":
        from fantasy_football.storage.sync import sync_parquet_prefix

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
        _analyze(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
