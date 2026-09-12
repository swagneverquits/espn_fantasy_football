import unittest
from datetime import datetime, timedelta, timezone

from fantasy_football.schedule.windows import (
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


class CacheTests(unittest.TestCase):
    def test_existing_lock_file_does_not_prevent_refresh(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        from fantasy_football.schedule import cache

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "schedule.json"
            lock = path.with_suffix(".lock")
            lock.write_bytes(b"0")
            games = []
            with (
                patch.object(cache, "CACHE_PATH", path),
                patch.object(cache, "LOCK_PATH", lock),
                patch.object(
                    cache, "fetch_nfl_game_starts", return_value=games
                ) as fetch,
            ):
                self.assertEqual(
                    cache.get_game_starts(
                        datetime.now(timezone.utc), refresh_seconds=7200
                    ),
                    ([], True),
                )
                self.assertEqual(
                    cache.get_game_starts(
                        datetime.now(timezone.utc), refresh_seconds=7200
                    ),
                    ([], False),
                )
                fetch.assert_called_once()

    def test_expired_cache_is_not_returned_while_lock_is_held(self):
        from contextlib import contextmanager
        from unittest.mock import patch

        from fantasy_football.schedule import cache

        @contextmanager
        def held():
            yield False

        with (
            patch.object(cache, "_read_cache", return_value=([], 0)),
            patch.object(cache, "_schedule_lock", held),
            patch.object(cache, "LOCK_WAIT_SECONDS", 0),
        ):
            with self.assertRaises(TimeoutError):
                cache.get_game_starts(datetime.now(timezone.utc), refresh_seconds=7200)
