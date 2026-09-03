import unittest
from datetime import datetime, timedelta, timezone

from fantasy_football.schedule import (
    active_window,
    build_game_windows,
    seconds_until_next_window,
)


class ScheduleTests(unittest.TestCase):
    def test_build_game_windows_merges_overlapping_games(self):
        first = datetime(2026, 9, 10, 20, tzinfo=timezone.utc)
        second = first + timedelta(hours=3)

        windows = build_game_windows([first, second])

        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0].start, first - timedelta(minutes=15))
        self.assertEqual(windows[0].end, second + timedelta(hours=4))

    def test_build_game_windows_preserves_gaps(self):
        first = datetime(2026, 9, 10, 20, tzinfo=timezone.utc)
        second = first + timedelta(hours=5)

        windows = build_game_windows([first, second])

        self.assertEqual(len(windows), 2)

    def test_window_helpers(self):
        start = datetime(2026, 9, 10, 20, tzinfo=timezone.utc)
        windows = build_game_windows([start])
        now = start - timedelta(minutes=10)

        self.assertIsNotNone(active_window(windows, now))
        self.assertEqual(
            seconds_until_next_window(windows, start - timedelta(hours=1)),
            45 * 60,
        )


if __name__ == "__main__":
    unittest.main()
