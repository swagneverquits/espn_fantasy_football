"""Polling workflow for ESPN Fantasy Football API snapshots."""

import logging
import time

from fantasy_football.config import LEAGUE_IDS
from fantasy_football.io import get_results_file
from fantasy_football.storage import (
    DEFAULT_INTERVAL_SECONDS,
    DEFAULT_RETRY_SECONDS,
    write_snapshot,
)

from .client import configured_cookies, fetch_league_data
from .parser import current_week, matchup_rows


def main(
    league: str,
    *,
    season: int = 2026,
    interval_seconds=DEFAULT_INTERVAL_SECONDS,
    retry_seconds=DEFAULT_RETRY_SECONDS,
    once=False,
):
    if league not in LEAGUE_IDS:
        raise ValueError(f"Unknown league '{league}'")
    espn_s2, swid = configured_cookies()
    while True:
        try:
            data = fetch_league_data(
                season, LEAGUE_IDS[league], espn_s2=espn_s2, swid=swid
            )
            week = current_week(data)
            path = get_results_file(season, week, league)
            path.parent.mkdir(parents=True, exist_ok=True)
            rows = write_snapshot(path, matchup_rows(data, matchup_period=week))
            logging.info("ESPN scrape complete; wrote %s row(s) to %s", rows, path)
            if once:
                return
            time.sleep(interval_seconds)
        except Exception:
            logging.exception("ESPN scrape failed")
            if once:
                raise
            time.sleep(retry_seconds)
