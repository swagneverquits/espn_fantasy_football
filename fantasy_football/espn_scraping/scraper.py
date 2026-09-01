"""Polling workflow for ESPN Fantasy Football API snapshots."""

import logging
import time

from fantasy_football.config import LEAGUE_IDS
from fantasy_football.io import get_results_file
from fantasy_football.storage import (
    DEFAULT_INTERVAL_SECONDS,
    DEFAULT_RETRY_SECONDS,
    write_snapshot,
    write_sqlite_snapshot,
)

from .client import fetch_league_data
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
    while True:
        try:
            data = fetch_league_data(season, LEAGUE_IDS[league])
            week = current_week(data)
            path = get_results_file(season, week, league)
            path.parent.mkdir(parents=True, exist_ok=True)
            frame = matchup_rows(data, matchup_period=week)
            rows = write_snapshot(path, frame)
            write_sqlite_snapshot(
                frame,
                provider="espn",
                league_id=LEAGUE_IDS[league],
                season=season,
                matchup_period=week,
                data=data,
            )
            logging.info("ESPN scrape complete; wrote %s row(s) to %s", rows, path)
            if once:
                return
            time.sleep(interval_seconds)
        except Exception:
            logging.exception("ESPN scrape failed")
            if once:
                raise
            time.sleep(retry_seconds)


from .client import fetch_league_data
