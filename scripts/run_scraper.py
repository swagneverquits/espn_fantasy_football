#!/usr/bin/env python3
"""
Entry point for running the ESPN fantasy football scraper.
"""

import logging
from src.scraper import main


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler()],
    )

    logging.info("🚀 Starting fantasy football scraper...")
    try:
        main()
    except KeyboardInterrupt:
        logging.info("🛑 Scraper stopped manually.")
    except Exception as e:
        logging.exception("❌ Scraper crashed: %s", e)
        raise
