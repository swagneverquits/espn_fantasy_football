"""Command-line wiring; configuration and dependencies load only when needed."""

import argparse
import logging
import os
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    from fantasy_football.storage.writer import ParquetSnapshotWriter


def _configured_writer(storage_mode: str = "local") -> "ParquetSnapshotWriter":
    """Resolve runtime storage settings before constructing the writer."""
    from fantasy_football.storage.writer import build_writer

    if storage_mode not in {"local", "gcs"}:
        raise ValueError("storage_mode must be 'local' or 'gcs'")
    if storage_mode == "local":
        if os.getenv("FANTASY_FOOTBALL_WORKER") != "1":
            logging.info("Snapshot destination: local path=%s", PARQUET_DIR)
        return build_writer()

    bucket = os.getenv("GCS_BUCKET")
    if not bucket:
        raise ValueError("GCS_BUCKET is required when storage_mode='gcs'")
    if os.getenv("FANTASY_FOOTBALL_WORKER") != "1":
        logging.info("Snapshot destination: GCS bucket=%s", bucket)
    return build_writer(bucket=bucket)


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
    selection = analyze.add_mutually_exclusive_group(required=True)
    selection.add_argument("--league", help="Configured league name.")
    selection.add_argument(
        "--all", action="store_true", help="Plot all configured leagues."
    )
    analyze.add_argument(
        "--provider",
        choices=("espn", "sleeper"),
        help="Filter --all by provider; defaults to ESPN for a single league.",
    )

    sync = commands.add_parser(
        "sync", help="Download one or all leagues for a week from GCS."
    )
    sync.add_argument("--bucket", required=True)
    sync.add_argument(
        "--provider",
        choices=("espn", "sleeper"),
        help="Required for one league; optionally filters --all.",
    )
    selection = sync.add_mutually_exclusive_group(required=True)
    selection.add_argument("--league-id", help="Provider league ID.")
    selection.add_argument(
        "--all", action="store_true", help="Sync all configured leagues concurrently."
    )
    sync.add_argument("--season", type=int, required=True)
    sync.add_argument("--week", type=int, required=True)
    sync.add_argument("--output-dir", type=Path, default=PARQUET_DIR)
    sync.add_argument("--tables", nargs="+", choices=PARQUET_TABLES)

    return parser


def _all_leagues(args: argparse.Namespace) -> list[tuple[str, str, str]]:
    """Resolve configured names and IDs, with optional provider filtering."""
    config = load_leagues(args.config)
    targets = []
    seen = set()
    for provider, leagues in (("espn", config.espn), ("sleeper", config.sleeper)):
        if args.provider is not None and args.provider != provider:
            continue
        for name, league_id in leagues.items():
            if (provider, league_id) not in seen:
                targets.append((provider, name, league_id))
                seen.add((provider, league_id))
    return targets


def _sync(args: argparse.Namespace) -> int:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from fantasy_football.storage.sync import sync_parquet_prefix

    targets = (
        _all_leagues(args)
        if args.all
        else [(args.provider, args.league_id, args.league_id)]
    )
    if not targets:
        logging.error("No configured leagues match the selection")
        return 1
    failed = False
    total = 0
    # Each league has a separate destination prefix and its own GCS client.
    with ThreadPoolExecutor(max_workers=min(8, len(targets))) as pool:
        futures = {
            pool.submit(
                sync_parquet_prefix,
                args.bucket,
                provider=provider,
                league_id=league_id,
                season=args.season,
                matchup_period=args.week,
                output_dir=args.output_dir,
                tables=args.tables,
            ): (provider, name)
            for provider, name, league_id in targets
        }
        for future in as_completed(futures):
            provider, name = futures[future]
            try:
                count = future.result()
                total += count
                logging.info("Synced %s/%s: %d new objects", provider, name, count)
            except Exception:
                failed = True
                logging.exception("Sync failed: %s/%s", provider, name)
    logging.info(
        "Downloaded %d new Parquet objects across %d leagues", total, len(targets)
    )
    return int(failed)


def _analyze(args: argparse.Namespace) -> int:
    from fantasy_football.plotting import generate_matchup_plots
    from fantasy_football.storage.duckdb import load_matchup_results

    if args.all:
        targets = _all_leagues(args)
    else:
        provider = args.provider or "espn"
        league_id = load_leagues(args.config).league_id(provider, args.league)
        targets = [(provider, args.league, league_id)]
    failed = False
    plotted = 0
    # Matplotlib has shared state, so rendering stays sequential.
    for provider, name, league_id in targets:
        try:
            data = load_matchup_results(
                PARQUET_DIR,
                provider=provider,
                league_id=league_id,
                season=args.season,
                matchup_period=args.week,
            )
            output = PLOTS_DIR / str(args.season)
            if args.all:
                output = output / provider
            output = output / name / f"week_{args.week}"
            paths = generate_matchup_plots(
                data, week=args.week, output_dir=output, league_name=name
            )
            for path in paths:
                print(path)
            plotted += len(paths)
        except FileNotFoundError:
            if not args.all:
                raise
            logging.warning("No local snapshots for %s/%s; skipping", provider, name)
        except Exception:
            if not args.all:
                raise
            failed = True
            logging.exception("Plotting failed: %s/%s", provider, name)
    if not plotted:
        logging.warning("No plots generated for the selected leagues")
    return int(failed or not plotted)


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
    )
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "scrape":
        from fantasy_football.runner import Poller, RunOptions, run_all

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
        Poller(scraper, _configured_writer(args.storage)).run(
            interval_seconds=options.interval_seconds,
            retry_seconds=options.retry_seconds,
            once=options.once,
            schedule_gate=options.schedule_gate,
        )
    elif args.command == "sync":
        if not args.all and args.provider is None:
            parser.error("--provider is required with --league-id")
        return _sync(args)
    else:
        return _analyze(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
