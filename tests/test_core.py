import unittest

import pandas as pd

from fantasy_football.analysis.transform import normalize_team_names


class CoreTests(unittest.TestCase):
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
