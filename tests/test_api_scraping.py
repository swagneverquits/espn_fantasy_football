import datetime
import unittest

from fantasy_football.scrapers.espn.client import build_league_url
from fantasy_football.scrapers.espn.parser import current_week, matchup_rows


class APIScrapingTests(unittest.TestCase):
    def setUp(self):
        self.data = {
            "scoringPeriodId": 3,
            "status": {"currentMatchupPeriod": 3},
            "teams": [
                {"id": 1, "name": "Fannin Boot"},
                {"id": 2, "name": "Pitts-uational Awareness"},
            ],
            "schedule": [
                {
                    "id": 10,
                    "matchupPeriodId": 3,
                    "away": {
                        "teamId": 1,
                        "totalPointsLive": 42.5,
                        "totalProjectedPointsLive": 101.0,
                        "winProbability": 0.54,
                    },
                    "home": {
                        "teamId": 2,
                        "totalPointsLive": 38.0,
                        "totalProjectedPointsLive": 98.0,
                        "winProbability": 0.46,
                    },
                },
                {
                    "id": 11,
                    "matchupPeriodId": 4,
                    "away": {
                        "teamId": 1,
                        "totalPointsLive": 0,
                        "totalProjectedPointsLive": 100,
                        "winProbability": 0.5,
                    },
                    "home": {
                        "teamId": 2,
                        "totalPointsLive": 0,
                        "totalProjectedPointsLive": 100,
                        "winProbability": 0.5,
                    },
                },
            ],
        }

    def test_build_league_url_repeats_views(self):
        league_id = 123456789
        url = build_league_url(2026, league_id, ("mMatchup", "mScoreboard"))
        self.assertIn(f"seasons/2026/segments/0/leagues/{league_id}", url)
        self.assertEqual(url.count("view="), 2)

    def test_current_week_uses_status(self):
        self.assertEqual(current_week(self.data), 3)

    def test_matchup_rows_maps_values_and_filters_period(self):
        timestamp = datetime.datetime(2026, 9, 1, tzinfo=datetime.timezone.utc)
        frame = matchup_rows(self.data, timestamp=timestamp, matchup_period=3)
        self.assertEqual(len(frame), 2)
        self.assertEqual(frame.loc[(timestamp, "Fannin Boot"), "Score"], 42.5)
        self.assertEqual(frame.loc[(timestamp, "Fannin Boot"), "WinChance"], 0.54)
        self.assertEqual(frame.loc[(timestamp, "Fannin Boot"), "Projected"], 101.0)

    def test_matchup_rows_skips_missing_probability(self):
        data = {
            **self.data,
            "schedule": [
                {
                    "id": 12,
                    "matchupPeriodId": 3,
                    "away": {"teamId": 1, "totalPointsLive": 1},
                    "home": {"teamId": 2, "totalPointsLive": 2, "winProbability": 0.5},
                }
            ],
        }
        frame = matchup_rows(data, matchup_period=3)
        self.assertEqual(len(frame), 1)
        self.assertEqual(
            frame.index.get_level_values("team").tolist(), ["Pitts-uational Awareness"]
        )


if __name__ == "__main__":
    unittest.main()
