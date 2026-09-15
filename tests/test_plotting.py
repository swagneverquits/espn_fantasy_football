import tempfile
import unittest
from pathlib import Path

import pandas as pd

from fantasy_football.plotting import generate_matchup_plots
from fantasy_football.plotting.matchups import normalize_team_names
from fantasy_football.plotting.renderer import _asymmetric_probability_scale
from fantasy_football.plotting.timeline import game_windows
from fantasy_football.plotting.swings import (
    largest_probability_swings,
    probability_swings,
)


class PlottingTests(unittest.TestCase):
    def test_probability_labels_thin_without_changing_bounds(self):
        narrow = _asymmetric_probability_scale(
            pd.Series([0.45, 0.55]), plot_width_pixels=600
        )
        wide = _asymmetric_probability_scale(
            pd.Series([0.0, 1.0]), plot_width_pixels=600
        )
        self.assertEqual(narrow[:2], (7.5, 7.5))
        self.assertEqual(wide[:2], (50.0, 50.0))
        self.assertIn("EVEN", narrow[3])
        self.assertIn("EVEN", wide[3])
        self.assertIn("100%", wide[3])
        self.assertEqual(narrow[4], (-5.0, 0.0, 5.0))

    def test_probability_labels_show_only_outer_and_midpoint_values(self):
        _, _, ticks, labels, _ = _asymmetric_probability_scale(
            pd.Series([0.40, 0.55]), plot_width_pixels=600
        )
        self.assertEqual(ticks, (-5.0, 0.0, 5.0, 10.0))
        self.assertEqual(labels, ("55%", "EVEN", "55%", "60%"))

        _, _, ticks, labels, _ = _asymmetric_probability_scale(
            pd.Series([0.40, 0.00]), plot_width_pixels=600
        )
        self.assertEqual(ticks, (0.0, 10.0, 20.0, 30.0, 40.0, 50.0))
        self.assertEqual(
            labels, ("EVEN", "60%", "70%", "80%", "90%", "100%")
        )

    def test_probability_labels_remain_independent_for_asymmetric_extents(self):
        _, _, ticks, labels, _ = _asymmetric_probability_scale(
            pd.Series([0.55, 0.25]), plot_width_pixels=600
        )
        self.assertEqual(
            ticks, (-5.0, 0.0, 5.0, 10.0, 15.0, 20.0, 25.0)
        )
        self.assertEqual(
            labels, ("55%", "EVEN", "55%", "60%", "65%", "70%", "75%")
        )

    def test_probability_labels_use_one_cadence_on_both_sides(self):
        _, _, ticks, labels, _ = _asymmetric_probability_scale(
            pd.Series([0.0, 0.70]), plot_width_pixels=600
        )
        self.assertEqual(
            ticks, (-20.0, -10.0, 0.0, 10.0, 20.0, 30.0, 40.0, 50.0)
        )
        self.assertEqual(
            labels, ("70%", "60%", "EVEN", "60%", "70%", "80%", "90%", "100%")
        )

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
                [times[1], 1, 11.0],
                [times[1], 2, 12.0],
                [times[2], 1, 10.0],
                [times[2], 2, 12.0],
            ],
            columns=["timestamp", "team_id", "score_live"],
        )
        windows = game_windows(data, 1800)
        self.assertEqual(windows, [(times[0], times[1])])

    def test_isolated_repeated_friday_pull_is_not_a_window(self):
        times = pd.to_datetime(
            [
                "2026-09-10 20:00",
                "2026-09-10 20:30",
                "2026-09-11 13:00",
                "2026-09-13 13:00",
                "2026-09-13 13:30",
            ]
        ).tz_localize("America/New_York")
        data = pd.DataFrame(
            [
                [times[0], 1, 0.0, 0.50],
                [times[0], 2, 0.0, 0.50],
                [times[1], 1, 4.0, 0.55],
                [times[1], 2, 0.0, 0.45],
                [times[2], 1, 4.0, 0.55],
                [times[2], 2, 0.0, 0.45],
                [times[3], 1, 4.0, 0.55],
                [times[3], 2, 0.0, 0.45],
                [times[4], 1, 10.0, 0.65],
                [times[4], 2, 0.0, 0.35],
            ],
            columns=["timestamp", "team_id", "score_live", "win_probability"],
        )
        windows = game_windows(data, 1800)
        self.assertEqual(
            windows,
            [(times[0], times[1]), (times[3], times[4])],
        )

    def test_sustained_window_without_matchup_changes_is_retained(self):
        times = pd.to_datetime(
            ["2026-09-09 20:00", "2026-09-09 20:30"]
        ).tz_localize("America/New_York")
        data = pd.DataFrame(
            [
                [times[0], 1, 0.0, 0.5],
                [times[0], 2, 0.0, 0.5],
                [times[1], 1, 0.0, 0.5],
                [times[1], 2, 0.0, 0.5],
            ],
            columns=["timestamp", "team_id", "score_live", "win_probability"],
        )
        self.assertEqual(game_windows(data, 1800), [(times[0], times[1])])

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

    def test_singleton_observations_are_not_activity_windows(self):
        times = pd.to_datetime(["2026-09-13 20:00", "2026-09-20 20:00"]).tz_localize(
            "America/New_York"
        )
        self.assertEqual(game_windows(pd.DataFrame({"timestamp": times}), 1800), [])
