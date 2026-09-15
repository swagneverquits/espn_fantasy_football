"""Command-line wiring; configuration and dependencies load only when needed."""

import argparse
import logging
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from time import perf_counter
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Literal

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


StorageMode = Literal["local", "gcs"]


def _configured_writer(storage_mode: StorageMode = "local") -> "ParquetSnapshotWriter":
    """Resolve runtime storage settings before constructing the writer."""
    from fantasy_football.storage.writer import build_writer

    if storage_mode == "local":
        if os.getenv("FANTASY_FOOTBALL_WORKER") != "1":
            logging.info("Snapshot destination: local path=%s", PARQUET_DIR)
        return build_writer()

    if storage_mode == "gcs":
        bucket = os.getenv("GCS_BUCKET")
        if not bucket:
            raise ValueError("GCS_BUCKET is required when storage_mode='gcs'")
        if os.getenv("FANTASY_FOOTBALL_WORKER") != "1":
            logging.info("Snapshot destination: GCS bucket=%s", bucket)
        return build_writer(bucket=bucket)

    raise ValueError("storage_mode must be 'local' or 'gcs'")


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


def _add_scrape_parser(commands: argparse._SubParsersAction) -> None:
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


def _add_analyze_parser(commands: argparse._SubParsersAction) -> None:
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
    analyze.add_argument(
        "--tag-swings",
        type=float,
        metavar="PP",
        help="Tag every win-probability swing of at least PP percentage points.",
    )


def _add_sync_parser(commands: argparse._SubParsersAction) -> None:
    sync = commands.add_parser("sync", help="Download one or all leagues from GCS.")
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
    sync.add_argument(
        "--week",
        type=int,
        help="Sync one week; omit to sync every week in the season.",
    )
    sync.add_argument("--output-dir", type=Path, default=PARQUET_DIR)
    sync.add_argument("--tables", nargs="+", choices=PARQUET_TABLES)


def _add_status_parser(commands: argparse._SubParsersAction) -> None:
    status = commands.add_parser("status", help="Show remote scraper worker status.")
    status.add_argument(
        "--watch",
        action="store_true",
        help="Refresh the dashboard until Ctrl+C; scraping continues independently.",
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
    _add_scrape_parser(commands)
    _add_analyze_parser(commands)
    _add_sync_parser(commands)
    _add_status_parser(commands)
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


def _analyze_league(
    target: tuple[str, str, str],
    *,
    season: int,
    week: int | str,
    include_provider: bool,
    tag_swings: float | None,
) -> tuple[str, str, Path, int, int, float, float]:
    """Load and render one league; this is the process-pool boundary."""
    from fantasy_football.plotting import generate_matchup_plots
    from fantasy_football.storage.duckdb import load_matchup_results

    provider, name, league_id = target
    load_started = perf_counter()
    data = load_matchup_results(
        PARQUET_DIR,
        provider=provider,
        league_id=league_id,
        season=season,
        matchup_period=week,
    )
    load_seconds = perf_counter() - load_started
    output = PLOTS_DIR / str(season)
    if include_provider:
        output = output / provider
    output = output / name / f"week_{week}"
    plot_started = perf_counter()
    paths = generate_matchup_plots(
        data,
        week=week,
        season=season,
        output_dir=output,
        league_name=name,
        tag_swings=tag_swings,
    )
    render_seconds = perf_counter() - plot_started
    return provider, name, output, len(paths), len(data), load_seconds, render_seconds


def _sync(args: argparse.Namespace) -> int:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from fantasy_football.storage.sync import sync_parquet_prefix
    from fantasy_football.terminal.sync import SyncDisplay

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
    # Match the default Google HTTP connection pool rather than creating
    # excess connections that urllib3 immediately discards.
    download_workers = min(10, max(4, len(targets) * 2))
    logging.info(
        "Sync parallelizing %d league coordinators across %d download workers",
        len(targets),
        download_workers,
    )
    with (
        SyncDisplay(targets) as display,
        ThreadPoolExecutor(max_workers=download_workers) as download_pool,
        ThreadPoolExecutor(max_workers=min(8, len(targets))) as pool,
    ):
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
                download_executor=download_pool,
                **(
                    {
                        "progress": lambda status, count, latest, p=provider, i=league_id: display.update(
                            p, i, status, count, latest
                        )
                    }
                    if display.enabled
                    else {}
                ),
            ): (provider, name, league_id)
            for provider, name, league_id in targets
        }
        for future in as_completed(futures):
            provider, name, league_id = futures[future]
            try:
                count = future.result()
                total += count
                if not display.enabled:
                    logging.info("Synced %s/%s: %d new objects", provider, name, count)
            except Exception:
                failed = True
                display.update(provider, league_id, "Failed", 0, None)
                logging.exception("Sync failed: %s/%s", provider, name)
    logging.info(
        "Downloaded %d new Parquet objects across %d leagues", total, len(targets)
    )
    return int(failed)


def _analyze(args: argparse.Namespace) -> int:
    from fantasy_football.terminal.analyze import AnalyzeDisplay

    if args.all:
        targets = _all_leagues(args)
    else:
        provider = args.provider or "espn"
        league_id = load_leagues(args.config).league_id(provider, args.league)
        targets = [(provider, args.league, league_id)]
    failed = False
    plotted = 0
    analysis_started = perf_counter()
    outputs: list[Path] = []

    with AnalyzeDisplay(targets) as display:

        def handle_result(
            result: tuple[str, str, Path, int, int, float, float],
        ) -> None:
            nonlocal plotted
            (
                provider,
                name,
                output,
                count,
                row_count,
                load_seconds,
                render_seconds,
            ) = result
            logging.info(
                "Analyze %s/%s week=%s loaded rows=%d in %.2fs; rendered plots=%d in %.2fs",
                provider,
                name,
                args.week,
                row_count,
                load_seconds,
                count,
                render_seconds,
            )
            display.update(
                provider,
                targets_by_key[(provider, name)],
                "Complete",
                rows=row_count,
                load_seconds=load_seconds,
                plots=count,
                render_seconds=render_seconds,
            )
            outputs.append(output)
            plotted += count

        targets_by_key = {
            (provider, name): league_id for provider, name, league_id in targets
        }

        if len(targets) == 1:
            try:
                handle_result(
                    _analyze_league(
                        targets[0],
                        season=args.season,
                        week=args.week,
                        include_provider=args.all,
                        tag_swings=args.tag_swings,
                    )
                )
            except FileNotFoundError:
                raise
            except Exception:
                raise
        else:
            max_workers = min(4, len(targets))
            logging.info(
                "Analyze parallelizing %d leagues across %d workers",
                len(targets),
                max_workers,
            )
            with ProcessPoolExecutor(max_workers=max_workers) as pool:
                futures = {
                    pool.submit(
                        _analyze_league,
                        target,
                        season=args.season,
                        week=args.week,
                        include_provider=args.all,
                        tag_swings=args.tag_swings,
                    ): target
                    for target in targets
                }
                for future in as_completed(futures):
                    provider, name, league_id = futures[future]
                    try:
                        handle_result(future.result())
                    except FileNotFoundError:
                        display.update(provider, league_id, "Skipped")
                        logging.warning(
                            "No local snapshots for %s/%s; skipping", provider, name
                        )
                    except Exception:
                        failed = True
                        display.update(provider, league_id, "Failed")
                        logging.exception("Plotting failed: %s/%s", provider, name)
    if display.enabled:
        display.console.print(display.final_table())
    for output in outputs:
        print(output)
    if not plotted:
        logging.warning("No plots generated for the selected leagues")
    logging.info(
        "Analyze complete: plots=%d leagues=%d elapsed=%.2fs",
        plotted,
        len(targets),
        perf_counter() - analysis_started,
    )
    return int(failed or not plotted)


def _scrape(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from fantasy_football.runtime.polling import Poller
    from fantasy_football.runtime.workers import RunOptions, run_all

    options = RunOptions(
        season=args.season,
        interval_seconds=args.interval,
        retry_seconds=args.retry_interval,
        once=args.once,
        schedule_gate=not args.no_schedule_gate,
        storage_mode=args.storage,
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

        league_id = args.league_id
        scraper = SleeperScraper(league_id, season=args.season)
    from fantasy_football.runtime.status import WorkerStatus

    worker_status = WorkerStatus(args.provider, str(league_id))
    Poller(scraper, _configured_writer(args.storage), status=worker_status).run(
        interval_seconds=options.interval_seconds,
        retry_seconds=options.retry_seconds,
        once=options.once,
        schedule_gate=options.schedule_gate,
    )
    return 0


def _status(args: argparse.Namespace) -> int:
    from fantasy_football.terminal.dashboard import show_status

    return show_status(load_leagues(args.config), watch=args.watch)


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
    )
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {
        "scrape": lambda: _scrape(args, parser),
        "status": lambda: _status(args),
        "sync": lambda: _sync(args),
        "analyze": lambda: _analyze(args),
    }
    if args.command == "sync" and not args.all and args.provider is None:
        parser.error("--provider is required with --league-id")
    return handlers[args.command]()


if __name__ == "__main__":
    raise SystemExit(main())
