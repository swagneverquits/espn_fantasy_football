import datetime
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from fantasy_football.constants import DEFAULT_SCHEDULE_REFRESH_SECONDS
from fantasy_football.scrapers.sleeper.parser import parse_snapshot
from fantasy_football.scrapers.sleeper.scraper import SleeperScraper
from fantasy_football.scrapers.sleeper.win_probability import sleeper_win_percentage
from fantasy_football.storage.writer import build_writer


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
        snapshot = parse_snapshot(
            data, league_id="123", season=2026, timestamp=int(timestamp.timestamp())
        )
        frame = snapshot.team_snapshots.set_index("team_id")
        self.assertEqual(len(frame), 2)
        self.assertEqual(frame.loc[1, "score_live"], 101.5)
        self.assertEqual(frame.loc[2, "opponent_id"], 1)
        self.assertIn("win_probability", frame.columns)


class SleeperRolloverTests(unittest.TestCase):
    def test_state_refresh_and_week_rollover(self):
        interval = DEFAULT_SCHEDULE_REFRESH_SECONDS
        with (
            patch(
                "fantasy_football.scrapers.sleeper.scraper.time.monotonic",
                side_effect=[0, 1, interval, 2 * interval],
            ),
            patch("fantasy_football.scrapers.sleeper.scraper.fetch_json") as fetch,
        ):
            fetch.side_effect = [
                {"week": 1},
                {"name": "First"},
                [],
                {"week": 1},
                {"week": 2},
                {"name": "Renamed"},
                [{"user_id": "new"}],
            ]
            scraper = SleeperScraper("123")
            self.assertEqual(scraper.get_league_metadata()["week"], 1)
            scraper.get_league_metadata()
            self.assertEqual(fetch.call_count, 3)
            scraper.get_league_metadata()
            self.assertEqual(fetch.call_count, 4)
            metadata = scraper.get_league_metadata()
            self.assertEqual(metadata["week"], 2)
            self.assertEqual(metadata["league"]["name"], "Renamed")
            self.assertEqual(fetch.call_count, 7)


class SleeperPlayerTests(unittest.TestCase):
    def test_invalid_probability_preserves_snapshot_and_defense(self):
        data = {
            "week": 1,
            "users": [],
            "rosters": [{"roster_id": 1}, {"roster_id": 2}],
            "matchups": [
                {
                    "roster_id": 1,
                    "matchup_id": 1,
                    "points": 120,
                    "starters": ["123", "PHI", "999", "0"],
                    "players_points": {"PHI": 12},
                },
                {"roster_id": 2, "matchup_id": 1, "points": 90, "starters": ["456"]},
            ],
            "player_data": {
                "projections": [
                    {"player_id": "123", "stats": {"pts_std": 100}},
                    {"player_id": "456", "stats": {"pts_std": 105}},
                ],
                "stats": [
                    {
                        "player_id": "PHI",
                        "player": {"first_name": "Philadelphia", "position": "DEF"},
                    }
                ],
            },
        }
        snapshot = parse_snapshot(data, league_id="123", season=2026)
        frame = snapshot.team_snapshots
        self.assertTrue(frame["win_probability"].isna().all())
        self.assertEqual(frame["score_live"].tolist(), [120, 90])
        with tempfile.TemporaryDirectory() as directory:
            build_writer(directory).write(snapshot)
            players = pd.read_parquet(
                next(Path(directory).rglob("player_snapshots/*.pq"))
            )
            self.assertEqual(set(players["player_id"]), {"123", "456", "999", "PHI"})
            defense = players.set_index("player_id").loc["PHI"]
            self.assertEqual(defense["points_live"], 12)
            self.assertEqual(defense["projected"], 0.0)

    def test_probability_valid_and_invalid_domains(self):
        self.assertEqual(sleeper_win_percentage(20, 100, 20, 100), (50, 50))
        self.assertEqual(sleeper_win_percentage(120, 120, 90, 90), (100, 0))
        self.assertEqual(sleeper_win_percentage(90, 90, 90, 90), (0, 0))
        for actual, projected in [(120, 100), (float("nan"), 100), (20, float("inf"))]:
            with self.subTest(actual=actual, projected=projected):
                self.assertIsNone(sleeper_win_percentage(actual, projected, 20, 100))


class ProjectionCompletenessTests(unittest.TestCase):
    def test_missing_starter_contributes_zero(self):
        from fantasy_football.scrapers.sleeper.parser import _projected_totals

        data = {
            "matchups": [{"roster_id": 1, "starters": ["a", "b", "0"]}],
            "player_data": {
                "projections": [{"player_id": "a", "stats": {"pts_std": 20}}]
            },
        }
        self.assertEqual(_projected_totals(data)[1], 20.0)
        data["player_data"]["projections"].append(
            {"player_id": "b", "stats": {"pts_std": 0}}
        )
        self.assertEqual(_projected_totals(data)[1], 20)


class ZeroProjectionTests(unittest.TestCase):
    def test_unavailable_values_and_valid_negative_projection(self):
        from fantasy_football.scrapers.sleeper.parser import _projection_or_zero

        for value in (None, float("nan"), float("inf"), "invalid"):
            self.assertEqual(_projection_or_zero(value), 0.0)
        self.assertEqual(_projection_or_zero(-2), -2.0)

    def test_missing_projection_allows_probability_calculation(self):
        snapshot = parse_snapshot(
            {
                "week": 1,
                "users": [],
                "rosters": [],
                "matchups": [
                    {
                        "roster_id": 1,
                        "matchup_id": 1,
                        "points": 0,
                        "starters": ["a", "missing"],
                    },
                    {"roster_id": 2, "matchup_id": 1, "points": 0, "starters": ["b"]},
                ],
                "player_data": {
                    "projections": [
                        {"player_id": "a", "stats": {"pts_std": 20}},
                        {"player_id": "b", "stats": {"pts_std": 20}},
                    ]
                },
            },
            league_id="123",
            season=2026,
        )
        self.assertEqual(snapshot.team_snapshots["projected_live"].tolist(), [20, 20])
        self.assertEqual(
            snapshot.team_snapshots["win_probability"].tolist(), [0.5, 0.5]
        )
        self.assertEqual(
            snapshot.player_snapshots.set_index("player_id").loc[
                "missing", "projected"
            ],
            0.0,
        )
