import logging
import time
from uuid import uuid4

import numpy as np

from .config import EMAIL, LEAGUE_IDS, PASSWORD
from .io import dump_html, get_results_path
from .scraping.browser import create_driver
from .scraping.espn import (
    get_nfl_week_from_scoreboard,
    login_to_espn,
    navigate_to_matchups,
    navigate_to_scoreboard,
    scrape_matchups,
)

DEFAULT_LEAGUE = "high_school"
DEFAULT_INTERVAL_SECONDS = 10
DEFAULT_REFRESH_SECONDS = 5 * 60
DEFAULT_RETRY_SECONDS = 30


def validate_credentials() -> None:
    if not EMAIL or not PASSWORD:
        raise ValueError(
            "ESPN_EMAIL and ESPN_PASSWORD must be set in environment variables or .env"
        )


def validate_league(league: str) -> int:
    try:
        return LEAGUE_IDS[league]
    except KeyError as exc:
        valid_leagues = ", ".join(sorted(LEAGUE_IDS))
        raise ValueError(f"Unknown league '{league}'. Expected one of: {valid_leagues}") from exc


def write_snapshot(results_file, df, run_id: str, scrape_id: int) -> int:
    if df.empty:
        logging.warning("Scrape %s returned no matchup rows; skipping write", scrape_id)
        return 0

    df = df.copy()
    df.index.names = ["time", "team"]
    df["run_id"] = run_id
    df["scrape_id"] = scrape_id
    df.to_csv(results_file, mode="a", header=not results_file.exists())
    return len(df)


def main(
    league: str = DEFAULT_LEAGUE,
    headless: bool = False,
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
    refresh_seconds: int = DEFAULT_REFRESH_SECONDS,
    retry_seconds: int = DEFAULT_RETRY_SECONDS,
    once: bool = False,
) -> None:
    validate_credentials()
    league_id = validate_league(league)
    run_id = str(uuid4())

    driver = create_driver(headless=headless)

    try:
        login_to_espn(driver, league_id, EMAIL, PASSWORD)
        navigate_to_scoreboard(driver)

        week = get_nfl_week_from_scoreboard(driver)
        results_file = get_results_path(league, week)
        logging.info("Saving results to %s", results_file)

        navigate_to_matchups(driver)
        last_refresh = time.time()
        scrape_id = 0

        while True:
            now = time.time()

            if now - last_refresh >= refresh_seconds:
                driver.refresh()
                logging.info("Refreshed driver")
                time.sleep(np.random.uniform(10, 15))
                last_refresh = time.time()

            scrape_id += 1
            try:
                df = scrape_matchups(driver)
                rows_written = write_snapshot(results_file, df, run_id, scrape_id)
                logging.info(
                    "Scrape %s complete; wrote %s row(s) to %s",
                    scrape_id,
                    rows_written,
                    results_file,
                )
            except Exception:
                logging.exception("Scrape %s failed", scrape_id)
                try:
                    dump_html(driver, f"scrape_{scrape_id}_failure.html")
                except Exception:
                    logging.exception("Failed to dump HTML after scrape failure")

                if once:
                    raise

                time.sleep(retry_seconds)
                driver.refresh()
                last_refresh = time.time()
                continue

            if once:
                return

            time.sleep(interval_seconds)
    finally:
        driver.quit()
