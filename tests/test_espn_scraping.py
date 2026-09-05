import datetime
import unittest

from fantasy_football.scrapers.espn.client import build_league_url
from fantasy_football.scrapers.espn.parser import (
    _player_data,
    current_week,
    parse_snapshot,
)


class ESPNScrapingTests(unittest.TestCase):
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
        snapshot = parse_snapshot(
            self.data,
            league_id="123",
            season=2026,
            timestamp=int(timestamp.timestamp()),
        )
        frame = snapshot.team_snapshots.set_index("team_id")
        self.assertEqual(len(frame), 2)
        self.assertEqual(frame.loc[1, "score_live"], 42.5)
        self.assertEqual(frame.loc[1, "win_probability"], 0.54)
        self.assertEqual(frame.loc[1, "projected_live"], 101.0)

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
        frame = parse_snapshot(data, league_id="123", season=2026).team_snapshots
        self.assertEqual(len(frame), 1)
        self.assertEqual(frame["team_id"].tolist(), [2])


class ESPNPlayerTests(unittest.TestCase):
    def test_espn_actual_and_projection_use_current_scoring_period(self):
        data = {
            "scoringPeriodId": 3,
            "schedule": [
                {
                    "matchupPeriodId": 2,
                    "id": 1,
                    "home": {
                        "teamId": 1,
                        "rosterForCurrentScoringPeriod": {
                            "entries": [
                                {
                                    "playerPoolEntry": {
                                        "player": {
                                            "id": 7,
                                            "stats": [
                                                {
                                                    "scoringPeriodId": 2,
                                                    "statSourceId": 1,
                                                    "appliedTotal": 99,
                                                },
                                                {
                                                    "scoringPeriodId": 3,
                                                    "statSourceId": 0,
                                                    "appliedTotal": 12,
                                                },
                                                {
                                                    "scoringPeriodId": 3,
                                                    "statSourceId": 1,
                                                    "appliedTotal": 18,
                                                    "appliedTotalCeiling": 24,
                                                },
                                            ],
                                        }
                                    }
                                },
                                {
                                    "playerPoolEntry": {
                                        "player": {
                                            "id": 8,
                                            "stats": [
                                                {
                                                    "scoringPeriodId": 1,
                                                    "statSourceId": 1,
                                                    "appliedTotal": 100,
                                                },
                                            ],
                                        }
                                    }
                                },
                            ]
                        },
                    },
                }
            ],
        }
        rows, _ = _player_data(data, "123", 2026, 2, 1)
        self.assertEqual(rows[0][9:], (12, 18, 24, 6))
        self.assertEqual(rows[1][9:], (None, None, None, None))
