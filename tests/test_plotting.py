import tempfile
import unittest
from pathlib import Path

import pandas as pd

from fantasy_football.plotting import generate_matchup_plots
from fantasy_football.plotting.matchups import normalize_team_names
from fantasy_football.plotting.timeline import game_windows
from fantasy_football.plotting.swings import (
    largest_probability_swings,
    probability_swings,
)


class PlottingTests(unittest.TestCase):
    def test_largest_probability_swings_preserves_ties(self):
        frame = pd.DataFrame(
            {
                "timestamp": [1, 2, 3, 4],
                "win_probability": [0.50, 0.55, 0.50, 0.55],
            }
        )
        swings = largest_probability_swings(frame)
        self.assertEqual(len(swings), 3)
        self.assertAlmostEqual(swings[0].delta_pp, 5.0)
        self.assertAlmostEqual(swings[1].delta_pp, -5.0)
        self.assertAlmostEqual(swings[2].delta_pp, 5.0)

    def test_largest_probability_swings_ignores_single_observation(self):
        frame = pd.DataFrame({"timestamp": [1], "win_probability": [0.5]})
        self.assertEqual(largest_probability_swings(frame), [])

    def test_probability_swings_uses_threshold_and_preserves_ties(self):
        frame = pd.DataFrame(
            {
                "timestamp": [1, 2, 3, 4],
                "win_probability": [0.50, 0.55, 0.50, 0.51],
            }
        )
        swings = probability_swings(frame, minimum_pp=5)
        self.assertEqual(len(swings), 2)
        self.assertAlmostEqual(swings[0].delta_pp, 5.0)
        self.assertAlmostEqual(swings[1].delta_pp, -5.0)

    def test_names_follow_team_ids_when_row_order_changes(self):
        data = pd.DataFrame(
            [
                [1, "Old A", 7, 1],
                [1, "B", 7, 2],
                [2, "B", 7, 2],
                [2, "New A", 7, 1],
            ],
            columns=["timestamp", "team_name", "matchup_id", "team_id"],
        )
        result = normalize_team_names(data)
        self.assertEqual(
            result.loc[result.team_id == 1, "team_name"].tolist(), ["New A", "New A"]
        )
        self.assertEqual(
            result.loc[result.team_id == 2, "team_name"].tolist(), ["B", "B"]
        )

    def test_render_normalized_data_to_png(self):
        data = pd.DataFrame(
            [
                [1789066800, 1, "A", 7, 20, 100, 0.6, "Test League"],
                [1789066800, 2, "B", 7, 18, 95, 0.4, "Test League"],
                [1789066830, 1, "A", 7, 21, 101, 0.7, "Test League"],
                [1789066830, 2, "B", 7, 18, 95, 0.3, "Test League"],
            ],
            columns=[
                "timestamp",
                "team_id",
                "team_name",
                "matchup_id",
                "score_live",
                "projected_live",
                "win_probability",
                "league_name",
            ],
        )
        with tempfile.TemporaryDirectory() as directory:
            paths = generate_matchup_plots(
                data, week=1, output_dir=directory, league_name="fallback"
            )
            self.assertEqual(len(paths), 1)
            self.assertEqual(Path(paths[0]).read_bytes()[:8], b"\x89PNG\r\n\x1a\n")


class WindowTests(unittest.TestCase):
    def test_repeated_isolated_terminal_snapshot_does_not_create_window(self):
        times = pd.to_datetime(
            [
                "2026-09-10 23:50",
                "2026-09-11 00:10",
                "2026-09-11 23:16",
            ]
        ).tz_localize("America/New_York")
        data = pd.DataFrame(
            [
                [times[0], 1, 10.0],
                [times[0], 2, 12.0],
                [times[1], 1, 10.0],
                [times[1], 2, 12.0],
                [times[2], 1, 10.0],
                [times[2], 2, 12.0],
            ],
            columns=["timestamp", "team_id", "score_live"],
        )
        windows = game_windows(data, 1800)
        self.assertEqual(windows, [(times[0], times[1])])

    def test_midnight_is_continuous_but_evening_is_separate(self):
        times = pd.to_datetime(
            [
                "2026-09-13 23:50",
                "2026-09-14 00:10",
                "2026-09-14 20:00",
                "2026-09-14 20:20",
            ]
        ).tz_localize("America/New_York")
        windows = game_windows(pd.DataFrame({"timestamp": times}), 1800)
        self.assertEqual(windows, [(times[0], times[1]), (times[2], times[3])])

    def test_same_weekday_in_later_week_is_not_discarded(self):
        times = pd.to_datetime(["2026-09-13 20:00", "2026-09-20 20:00"]).tz_localize(
            "America/New_York"
        )
        self.assertEqual(len(game_windows(pd.DataFrame({"timestamp": times}), 1800)), 2)
