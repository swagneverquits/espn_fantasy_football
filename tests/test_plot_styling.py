import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import matplotlib.pyplot as plt
import pandas as pd

from fantasy_football.plotting.plotting import plot_matchup


class PlotStylingTests(unittest.TestCase):
    def test_temporal_ruler_and_centered_endpoint_labels(self):
        rows = []
        for stamp in (1788999000, 1789009800, 1789085400, 1789096200):
            for team, score, projection, probability in (
                (1, 0, 102.5, 0.53),
                (2, 4.1, 98, 0.47),
            ):
                rows.append((stamp, team, str(team), score, projection, probability))
        data = pd.DataFrame(
            rows,
            columns=[
                "timestamp",
                "team_id",
                "team_name",
                "score_live",
                "projected_live",
                "win_probability",
            ],
        )
        with tempfile.TemporaryDirectory() as directory:
            with patch("fantasy_football.plotting.plotting.plt.close"):
                plot_matchup(
                    data,
                    league_name="Test",
                    week=1,
                    matchup=1,
                    savepath=Path(directory) / "plot.png",
                    window_gap_seconds=4 * 3600,
                )
                fig = plt.gcf()
            try:
                fig.canvas.draw()
                edge, points = fig.axes[:2], fig.axes[2:]
                for upper, lower in zip(edge, points):
                    self.assertFalse(upper.spines["bottom"].get_visible())
                    self.assertFalse(lower.spines["bottom"].get_visible())
                    self.assertEqual(
                        list(upper.get_xticks(minor=True)),
                        list(lower.get_xticks(minor=True)),
                    )
                    for ax in (upper, lower):
                        self.assertTrue(
                            all(
                                not tick.tick1line.get_visible()
                                for tick in ax.xaxis.get_major_ticks()
                                + ax.xaxis.get_minor_ticks()
                            )
                        )
                self.assertEqual(
                    [tick.get_text() for tick in edge[0].get_yticklabels()],
                    ["60%", "55%", "Even", "55%", "60%"],
                )
                labels = {text.get_text(): text for text in points[-1].texts}
                renderer = fig.canvas.get_renderer()
                for score, projected in (("0.0", "Proj 102.5"), ("4.1", "Proj 98.0")):
                    first, second = [
                        labels[value].get_window_extent(renderer)
                        for value in (score, projected)
                    ]
                    self.assertAlmostEqual(
                        (first.x0 + first.x1) / 2, (second.x0 + second.x1) / 2
                    )
                    self.assertLessEqual(second.x1, fig.bbox.x1)
                    self.assertLess(
                        labels[projected].get_fontsize(), labels[score].get_fontsize()
                    )
            finally:
                plt.close(fig)
