"""Polling workflow for Sleeper matchup snapshots."""

import logging
import time

from fantasy_football.io import get_results_file
from fantasy_football.storage import (
    DEFAULT_INTERVAL_SECONDS,
    DEFAULT_RETRY_SECONDS,
    write_snapshot,
    write_sqlite_snapshot,
)

from .client import fetch_league_data
from .parser import matchup_rows


def main(
    league_id: str,
    *,
    season: int = 2026,
    interval_seconds=DEFAULT_INTERVAL_SECONDS,
    retry_seconds=DEFAULT_RETRY_SECONDS,
    once=False,
):
    while True:
        try:
            data = fetch_league_data(league_id)
            week = data["week"]
            path = get_results_file(season, week, f"sleeper_{league_id}")
            path.parent.mkdir(parents=True, exist_ok=True)
            frame = matchup_rows(data, matchup_period=week)
            rows = write_snapshot(path, frame)
            write_sqlite_snapshot(
                frame,
                provider="sleeper",
                league_id=league_id,
                season=season,
                matchup_period=week,
                data=data,
            )
            logging.info("Sleeper scrape complete; wrote %s row(s) to %s", rows, path)
            if once:
                return
            time.sleep(interval_seconds)
        except Exception:
            logging.exception("Sleeper scrape failed")
            if once:
                raise
            time.sleep(retry_seconds)



