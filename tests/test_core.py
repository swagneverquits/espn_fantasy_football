import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

os.environ.setdefault("ESPN_EMAIL", "test@example.com")
os.environ.setdefault("ESPN_PASSWORD", "password")
os.environ.setdefault("ESPN_LEAGUE_ID_COLLEGE", "1")
os.environ.setdefault("ESPN_LEAGUE_ID_HIGH_SCHOOL", "2")
os.environ.setdefault("ESPN_LEAGUE_ID_CHARTER", "3")

from fantasy_football import io
from fantasy_football.analysis.transform import normalize_team_names


class CoreTests(unittest.TestCase):
    def test_load_results_uses_expected_results_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            results_dir = Path(tmpdir) / "results"
            csv_path = results_dir / "2026" / "college" / "week_1.csv"
            csv_path.parent.mkdir(parents=True)
            csv_path.write_text(
                "time,team,Matchup,Score,Projected,WinChance\n"
                "2026-09-01 12:00:00,Team A,0,10,20,0.5\n",
                encoding="utf-8",
            )

            with patch.object(io, "RESULTS_DIR", results_dir):
                df = io.load_results(2026, 1, "college")

        self.assertEqual(df.index.names, ["time", "team"])
        self.assertIsInstance(df.index.get_level_values("time")[0], pd.Timestamp)
        self.assertIn("date", df.columns)

    def test_normalize_team_names_uses_latest_name_per_slot(self):
        df = pd.DataFrame(
            [
                ["2026-09-01 12:00:00", "Old A", 0, 10],
                ["2026-09-01 12:00:00", "Team B", 0, 12],
                ["2026-09-01 12:10:00", "New A", 0, 14],
                ["2026-09-01 12:10:00", "Team B", 0, 15],
            ],
            columns=["time", "team", "Matchup", "Score"],
        )
        df["time"] = pd.to_datetime(df["time"])
        df = df.set_index(["time", "team"])

        teams = normalize_team_names(df).reset_index()["team"].tolist()

        self.assertEqual(teams.count("New A"), 2)
        self.assertEqual(teams.count("Team B"), 2)
        self.assertNotIn("Old A", teams)


if __name__ == "__main__":
    unittest.main()
