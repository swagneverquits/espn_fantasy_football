#!/usr/bin/env python3
"""Run the ESPN Fantasy Football JSON API scraper."""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fantasy_football.config import LEAGUE_IDS
from fantasy_football.espn_scraping.scraper import main

parser = argparse.ArgumentParser(description="Run the ESPN Fantasy API scraper.")
parser.add_argument("--league", choices=sorted(LEAGUE_IDS), required=True)
parser.add_argument("--season", type=int, default=2026)
parser.add_argument("--interval", type=int, default=10)
parser.add_argument("--retry-interval", type=int, default=30)
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
