import logging
import time

import numpy as np

from .config import EMAIL, LEAGUE_IDS, PASSWORD
from .utils.browser_utils import create_driver
from .utils.io_utils import get_results_path
from .utils.scraper_utils import (
    get_nfl_week_from_scoreboard,
    login_to_espn,
    navigate_to_matchups,
    navigate_to_scoreboard,
    scrape_matchups,
)

LEAGUE = "high_school"


def main():
    headless = False
    league_id = LEAGUE_IDS[LEAGUE]

    driver = create_driver(headless=headless)

    # log in to ESPN
    login_to_espn(driver, league_id, EMAIL, PASSWORD)

    # navigate to scoreboard
    navigate_to_scoreboard(driver)

    # get the current week
    week = get_nfl_week_from_scoreboard(driver)

    results_file = get_results_path(LEAGUE, week)
    logging.info(f"Saving results to {results_file}")

    # navigate to the fantasy cast
    navigate_to_matchups(driver)

    try:
        last_refresh = time.time()

        while True:
            now = time.time()

            if now - last_refresh >= 5 * 60:
                driver.refresh()
                logging.info(f"Refreshed driver")
                time.sleep(np.random.uniform(10, 15))
                last_refresh = now

            df = scrape_matchups(driver)
            df.index.names = ["time", "team"]
            df.to_csv(results_file, mode="a", header=not results_file.exists())
            time.sleep(10)
    finally:
        driver.quit()
