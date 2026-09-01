#!/usr/bin/env python3
"""Run the ESPN Fantasy Football JSON API scraper."""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fantasy_football.config import LEAGUE_IDS
from fantasy_football.constants import DEFAULT_INTERVAL_SECONDS, DEFAULT_RETRY_SECONDS
from fantasy_football.scrapers.espn.scraper import main

parser = argparse.ArgumentParser(description="Run the ESPN Fantasy API scraper.")
parser.add_argument("--league", choices=sorted(LEAGUE_IDS), required=True)
parser.add_argument("--season", type=int, default=2026)
parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_SECONDS)
parser.add_argument("--retry-interval", type=int, default=DEFAULT_RETRY_SECONDS)
parser.add_argument("--once", action="store_true")
args = parser.parse_args()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
main(
    league=args.league,
    season=args.season,
    interval_seconds=args.interval,
    retry_seconds=args.retry_interval,
    once=args.once,
)
