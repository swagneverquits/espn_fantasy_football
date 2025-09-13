import logging

from selenium import webdriver
from selenium.webdriver.chrome.options import Options


def create_driver(headless: bool = True) -> webdriver.Chrome:
    """Initialize a Chrome driver, optionally headless."""
    options = Options()
    if headless:
        options.add_argument("--headless=new")  # modern headless mode
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(options=options)  # auto-manages driver if Selenium >=4.6
    logging.info("✅ Chrome driver initialized (%s)", "headless" if headless else "visible")
    return driver
