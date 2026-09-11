import io
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from rich.console import Console

from fantasy_football.config import LeagueConfig
from fantasy_football.scrapers.schedule.scraper import NFLGame
from fantasy_football.status import dashboard


class DashboardTests(unittest.TestCase):
    def render(self, state="Idle", age=0, kickoff_hours=2, missing_cache=False):
        config = LeagueConfig({"a": "1", "b": "2", "c": "3"}, {"d": "4", "e": "5"})
        now = datetime.now(timezone.utc)
        cached = ([NFLGame(now + timedelta(hours=kickoff_hours), 1)], time.time())
        with (
            patch(
                "fantasy_football.status.read_status",
                return_value={"status": state, "heartbeat": time.time() - age},
            ),
            patch(
                "fantasy_football.scrapers.schedule.cache.read_cached_schedule",
                return_value=None if missing_cache else cached,
            ),
        ):
            output = io.StringIO()
            Console(file=output, width=150).print(dashboard(config))
            return output.getvalue()

    def test_idle_shows_both_tables(self):
        output = self.render()
        self.assertIn("Upcoming NFL windows", output)
        self.assertIn("Scraper status", output)
        self.assertIn("Week", output)
        self.assertNotIn("NFL week", output)
        self.assertNotIn("#", output)

    def test_active_and_unhealthy_workers_hide_windows(self):
        for state in ("Scraping", "Waiting", "Retrying", "Stopped", "Starting"):
            with self.subTest(state=state):
                self.assertNotIn("Upcoming NFL windows", self.render(state=state))
        self.assertNotIn("Upcoming NFL windows", self.render(age=60))
        self.assertNotIn("Upcoming NFL windows", self.render(kickoff_hours=0))

    def test_missing_cache_keeps_worker_table(self):
        output = self.render(missing_cache=True)
        self.assertIn("schedule cache unavailable", output)
        self.assertIn("Scraper status", output)
