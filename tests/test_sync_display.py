import unittest
from unittest.mock import Mock

from fantasy_football.terminal.sync import SyncDisplay


class SyncDisplayTests(unittest.TestCase):
    def test_success_and_failure_times(self):
        display = SyncDisplay([("espn", "charter", "1")])
        display.enabled = True
        display.live = Mock()
        display.update("espn", "1", "Syncing", 3, 1788999075)
        row = display.rows[("espn", "1")]
        self.assertEqual(row[4], "--")
        self.assertEqual(row[5], "09/09 20:11:15")
        display.update("espn", "1", "Failed", 0, None)
        self.assertEqual(row[3:5], ["3", "--"])
        display.update("espn", "1", "Synced", 3, 1788999075)
        self.assertNotEqual(row[4], "--")

    def test_redirected_output_does_not_render(self):
        display = SyncDisplay([("espn", "charter", "1")])
        display.enabled = False
        display.live = Mock()
        with display:
            display.update("espn", "1", "Synced", 0, None)
        display.live.start.assert_not_called()
        display.live.update.assert_not_called()
