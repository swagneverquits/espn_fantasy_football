import tempfile
import unittest
from pathlib import Path

import pandas as pd

from fantasy_football.plotting import generate_matchup_plots
from fantasy_football.plotting.plotting import normalize_team_names


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
