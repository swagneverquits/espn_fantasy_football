"""Polling workflow for ESPN Fantasy Football API snapshots."""

import logging
import time
from uuid import uuid4

from fantasy_football.config import LEAGUE_IDS
from fantasy_football.io import get_results_file
from fantasy_football.scraper import (
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
    try:
        league_id = LEAGUE_IDS[league]
    except KeyError as exc:
        raise ValueError(f"Unknown league '{league}'") from exc
    espn_s2, swid = configured_cookies()
    run_id = str(uuid4())
    scrape_id = 0
    while True:
        scrape_id += 1
        try:
            data = fetch_league_data(season, league_id, espn_s2=espn_s2, swid=swid)
            week = current_week(data)
            results_file = get_results_file(season, week, league)
            results_file.parent.mkdir(parents=True, exist_ok=True)
            rows_written = write_snapshot(
                results_file, matchup_rows(data, matchup_period=week), run_id, scrape_id
            )
            logging.info(
                "API scrape %s complete; wrote %s row(s) to %s",
                scrape_id,
                rows_written,
                results_file,
            )
            if once:
                return
            time.sleep(interval_seconds)
        except Exception:
            logging.exception("API scrape %s failed", scrape_id)
            if once:
                raise
            time.sleep(retry_seconds)
