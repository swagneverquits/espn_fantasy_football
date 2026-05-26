#!/usr/bin/env python3
"""
Entry point for running the ESPN fantasy football scraper.
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fantasy_football.config import LEAGUE_IDS
from fantasy_football.scraper import (
    DEFAULT_INTERVAL_SECONDS,
    DEFAULT_LEAGUE,
    DEFAULT_REFRESH_SECONDS,
    DEFAULT_RETRY_SECONDS,
    main,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the ESPN fantasy scraper.")
    parser.add_argument("--league", choices=sorted(LEAGUE_IDS), default=DEFAULT_LEAGUE)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_SECONDS)
    parser.add_argument("--refresh-interval", type=int, default=DEFAULT_REFRESH_SECONDS)
    parser.add_argument("--retry-interval", type=int, default=DEFAULT_RETRY_SECONDS)
    parser.add_argument("--once", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler()],
    )

    args = parse_args()
    logging.info("Starting fantasy football scraper")
    try:
        main(
            league=args.league,
            headless=args.headless,
            interval_seconds=args.interval,
            refresh_seconds=args.refresh_interval,
            retry_seconds=args.retry_interval,
            once=args.once,
        )
    except KeyboardInterrupt:
        logging.info("Scraper stopped manually")
    except Exception:
        logging.exception("Scraper crashed")
        raise
