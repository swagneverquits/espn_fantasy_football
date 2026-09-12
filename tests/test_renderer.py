import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import matplotlib.pyplot as plt
import pandas as pd
from PIL import Image

from fantasy_football.plotting import generate_matchup_plots
from fantasy_football.plotting.renderer import plot_matchup


class PortraitTests(unittest.TestCase):
    def data(self):
        return pd.DataFrame(
            [
                [stamp, team, str(team), 5, score, 100, probability, "Test", 2026]
                for stamp in (1788999000, 1788999030, 1789085400, 1789085430)
                for team, score, probability in ((1, 0, 0.53), (2, 4.1, 0.47))
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
                "season",
            ],
        )

    def test_portrait_dimensions_shared_continuous_time_and_scale(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("matplotlib.pyplot.close"):
                path = plot_matchup(
                    self.data(),
                    league_name="Test",
                    week=1,
                    matchup=5,
                    savepath=Path(directory) / "portrait.png",
                )
                fig = plt.gcf()
            try:
                with Image.open(path) as image:
                    self.assertEqual(image.size[0], 1080)
                    self.assertGreater(image.size[1], 0)
                probability, points = fig.axes
                self.assertEqual(probability.get_ylim(), points.get_ylim())
                self.assertTrue(probability.yaxis_inverted())
                self.assertLess(
                    abs(probability.get_ylim()[1] - probability.get_ylim()[0]), 1
                )
                self.assertEqual(points.get_xlim()[0], 0)
                self.assertEqual(
                    [x.get_text() for x in probability.get_xticklabels()],
                    ["55%", "EVEN"],
                )
                self.assertAlmostEqual(
                    probability.get_position().height, points.get_position().height
                )
                self.assertAlmostEqual(
                    probability.get_position().y0, points.get_position().y0
                )
                self.assertLess(probability.get_position().x1, points.get_position().x0)
            finally:
                plt.close(fig)

    def test_default_plot_output_uses_portrait_renderer(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = generate_matchup_plots(
                self.data(),
                week=1,
                league_name="Test",
                output_dir=directory,
            )
            self.assertEqual(paths[0].name, "matchup1.png")
