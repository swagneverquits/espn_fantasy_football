import datetime
import logging
import re
import time

import numpy as np
from selenium.webdriver import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.select import Select
from selenium.webdriver.support.wait import WebDriverWait


def wait_for_element(driver, by, selector, timeout=20):
    """Wait until an element is present and return it."""
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((by, selector))
    )


def login_to_espn(driver: WebDriver, league_id: int, email: str, password: str):
    league_url = f"https://fantasy.espn.com/football/league?leagueId={league_id}"
    driver.get(league_url)

    # Wait for iframe and switch
    WebDriverWait(driver, 20).until(
        EC.presence_of_all_elements_located((By.XPATH, "(//iframe)"))
    )
    driver.switch_to.frame(driver.find_elements(By.XPATH, "(//iframe)")[0])
    time.sleep(np.random.uniform(1, 1.5))

    # Email entry
    email_input = wait_for_element(
        driver, By.XPATH, '//*[@id="InputIdentityFlowValue"]'
    )
    for c in email:
        email_input.send_keys(c)
        time.sleep(np.random.uniform(0.03, 0.04))

    time.sleep(np.random.uniform(1, 1.5))
    email_input.send_keys(Keys.ENTER)
    time.sleep(np.random.uniform(1, 1.5))

    # Password entry
    password_input = wait_for_element(driver, By.XPATH, '//*[@id="InputPassword"]')
    for c in password:
        password_input.send_keys(c)
        time.sleep(np.random.uniform(0.03, 0.04))

    time.sleep(np.random.uniform(1, 1.5))
    password_input.send_keys(Keys.ENTER)

    logging.info("Login submitted")

    time.sleep(np.random.uniform(5, 10))
    return driver


def navigate_to_scoreboard(driver, timeout: int = 10):
    driver.refresh()
    time.sleep(np.random.uniform(3, 4))

    tab = WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable(
            (By.CSS_SELECTOR, 'a[href*="/football/league/scoreboard"]')
        )
    )
    tab.click()
    return driver


def navigate_to_matchups(driver, timeout: int = 10):
    driver.refresh()
    time.sleep(np.random.uniform(3, 4))

    tab = WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable(
            (By.CSS_SELECTOR, 'a[href*="/football/fantasycast"]')
        )
    )
    tab.click()
    time.sleep(np.random.uniform(10, 15))
    return driver


def get_nfl_week_from_scoreboard(driver: WebDriver, timeout: int = 10) -> int:
    """
    Grab the current week from ESPN fantasy scoreboard page via the week dropdown.
    """

    # wait for the week dropdown <select> to load
    time.sleep(np.random.uniform(2, 3))
    select_elem = WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "select.dropdown__select"))
    )

    # wrap with Select to easily get the selected option
    select = Select(select_elem)
    selected_text = select.first_selected_option.text.strip()  # e.g. "NFL Week 2"

    match = re.search(r"Week\s+(\d+)", selected_text, re.IGNORECASE)
    if not match:
        raise ValueError(f"Could not parse week from dropdown text: '{selected_text}'")
    return int(match.group(1))


def scrape_matchups(driver):
    """Scrape matchup data and return it as a DataFrame."""
    import pandas as pd  # local import avoids circular deps

    matchups = driver.find_elements(
        By.XPATH, "//*[contains(@class, 'carousel__slide')]"
    )
    team_dicts = {}

    for i, matchup in enumerate(matchups):
        timestamp = datetime.datetime.now().astimezone()
        matchup.click()

        elements = driver.find_elements(
            By.XPATH, '//div[contains(@class, "h2h-matchup-header")]'
        )

        for j, element in enumerate(elements):
            side = "r" if j == 0 else "l"
            team_name = element.find_element(
                By.XPATH, './/span[contains(@class, "teamName")]'
            ).text

            team_dict = {
                "Matchup": i,
                "Score": float(element.find_element(By.XPATH, ".//h2").text),
                "WinChance": float(
                    element.find_element(
                        By.XPATH, f'//*[contains(@class, "p{side}2 totalPerc")]'
                    ).text.replace("%", "")
                )
                / 100.0,
                "Projected": float(
                    element.find_elements(
                        By.XPATH, f'//div[contains(text(), "Proj Total")]//span'
                    )[j].text
                ),
            }
            team_dicts[(timestamp, team_name)] = team_dict
        time.sleep(np.random.uniform(0.25, 0.75))

    df = pd.DataFrame(team_dicts).T
    return df
