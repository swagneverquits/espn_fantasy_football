import tempfile
import unittest
from pathlib import Path

import pandas as pd

from fantasy_football.plotting import generate_matchup_plots
from fantasy_football.plotting.plotting import _game_windows, normalize_team_names


class PlottingTests(unittest.TestCase):
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
    def test_midnight_is_continuous_but_evening_is_separate(self):
        times = pd.to_datetime(
            [
                "2026-09-13 23:50",
                "2026-09-14 00:10",
                "2026-09-14 20:00",
                "2026-09-14 20:20",
            ]
        ).tz_localize("America/New_York")
        windows = _game_windows(pd.DataFrame({"timestamp": times}), 1800)
        self.assertEqual(windows, [(times[0], times[1]), (times[2], times[3])])

    def test_same_weekday_in_later_week_is_not_discarded(self):
        times = pd.to_datetime(["2026-09-13 20:00", "2026-09-20 20:00"]).tz_localize(
            "America/New_York"
        )
        self.assertEqual(
            len(_game_windows(pd.DataFrame({"timestamp": times}), 1800)), 2
        )


class EdgeScaleTests(unittest.TestCase):
    def test_symmetric_padded_zoom_and_labels(self):
        from fantasy_football.plotting.plotting import _edge_scale

        limit, ticks, labels = _edge_scale(pd.Series([0.4, 0.5, 0.6]))
        self.assertEqual(limit, 15)
        self.assertEqual(ticks, (-15, -7.5, 0, 7.5, 15))
        self.assertEqual(labels, ("65%", "57.5%", "Even", "57.5%", "65%"))

    def test_minimum_range_full_scale_and_missing_data(self):
        from fantasy_football.plotting.plotting import _edge_scale

        self.assertEqual(_edge_scale(pd.Series([0.5, 0.501]))[0], 10)
        self.assertEqual(_edge_scale(pd.Series([0.5]), True)[0], 50)
        self.assertEqual(_edge_scale(pd.Series([0, 1]))[0], 50)
        self.assertEqual(_edge_scale(pd.Series([None, float("inf")]))[0], 50)
