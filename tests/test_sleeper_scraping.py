import datetime
import unittest

from fantasy_football.scrapers.sleeper.parser import matchup_rows


class SleeperScrapingTests(unittest.TestCase):
    def test_matchup_rows_normalizes_rosters(self):
        data = {
            "week": 1,
            "users": [
                {
                    "user_id": "u1",
                    "display_name": "Michael",
                    "metadata": {"team_name": "Team One"},
                },
                {"user_id": "u2", "display_name": "Alex", "metadata": {}},
            ],
            "rosters": [
                {"roster_id": 1, "owner_id": "u1"},
                {"roster_id": 2, "owner_id": "u2"},
            ],
            "matchups": [
                {"roster_id": 1, "matchup_id": 3, "points": 101.5},
                {"roster_id": 2, "matchup_id": 3, "points": 98.0},
            ],
        }
        timestamp = datetime.datetime(2026, 9, 1, tzinfo=datetime.timezone.utc)
        frame = matchup_rows(data, timestamp=timestamp)
        self.assertEqual(len(frame), 2)
        self.assertEqual(frame.loc[(timestamp, "Team One"), "Score"], 101.5)
        self.assertEqual(frame.loc[(timestamp, "Alex"), "opponent_id"], 1)
        self.assertIn("WinChance", frame.columns)


if __name__ == "__main__":
    unittest.main()
