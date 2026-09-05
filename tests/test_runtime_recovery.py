"""Regression coverage for unattended polling and interrupted storage operations."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd

from fantasy_football.cli import _run_all, build_parser
from fantasy_football.constants import DEFAULT_SCHEDULE_REFRESH_SECONDS
from fantasy_football.scrapers.sleeper.parser import matchup_rows
from fantasy_football.scrapers.sleeper.scraper import SleeperScraper
from fantasy_football.scrapers.sleeper.win_probability import sleeper_win_percentage
from fantasy_football.storage.normalization import player_data
from fantasy_football.storage.pipeline import build_writer
from fantasy_football.storage.sync import sync_parquet_prefix


class WorkerTests(unittest.TestCase):
    def test_once_waits_for_all_successful_workers(self):
        first, second = Mock(), Mock()
        first.poll.return_value = 0
        second.poll.side_effect = [None, 0]
        with (
            patch("fantasy_football.cli.ESPN_LEAGUES", {"a": "1", "b": "2"}),
            patch("fantasy_football.cli.SLEEPER_LEAGUES", {}),
            patch("fantasy_football.cli.subprocess.Popen", side_effect=[first, second]),
            patch("fantasy_football.cli.time.sleep"),
        ):
            result = _run_all(build_parser().parse_args(["scrape", "all", "--once"]))
        self.assertEqual(result, 0)
        second.terminate.assert_not_called()

    def test_failed_worker_stops_remaining_workers(self):
        for flags in ([], ["--once"]):
            with self.subTest(flags=flags):
                first, second = Mock(), Mock()
                first.poll.return_value = 2
                second.poll.return_value = None
                with (
                    patch("fantasy_football.cli.ESPN_LEAGUES", {"a": "1", "b": "2"}),
                    patch("fantasy_football.cli.SLEEPER_LEAGUES", {}),
                    patch(
                        "fantasy_football.cli.subprocess.Popen",
                        side_effect=[first, second],
                    ),
                ):
                    result = _run_all(
                        build_parser().parse_args(["scrape", "all", *flags])
                    )
                self.assertEqual(result, 2)
                second.terminate.assert_called_once()


class SleeperRolloverTests(unittest.TestCase):
    def test_state_refresh_and_week_rollover(self):
        interval = DEFAULT_SCHEDULE_REFRESH_SECONDS
        with (
            patch("fantasy_football.scrapers.sleeper.scraper.configured_writer"),
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


class PlayerAndProbabilityTests(unittest.TestCase):
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
        frame = matchup_rows(data)
        self.assertTrue(frame["WinChance"].isna().all())
        self.assertEqual(frame["Score"].tolist(), [120, 90])
        with tempfile.TemporaryDirectory() as directory:
            build_writer(directory).write(
                frame,
                provider="sleeper",
                league_id="123",
                season=2026,
                matchup_period=1,
                data=data,
            )
            players = pd.read_parquet(
                next(Path(directory).rglob("player_snapshots/*.pq"))
            )
            self.assertEqual(set(players["player_id"]), {"123", "456", "999", "PHI"})
            defense = players.set_index("player_id").loc["PHI"]
            self.assertEqual(defense["points_live"], 12)
            self.assertTrue(pd.isna(defense["projected"]))

    def test_probability_valid_and_invalid_domains(self):
        self.assertEqual(sleeper_win_percentage(20, 100, 20, 100), (50, 50))
        self.assertEqual(sleeper_win_percentage(120, 120, 90, 90), (100, 0))
        self.assertEqual(sleeper_win_percentage(90, 90, 90, 90), (0, 0))
        for actual, projected in [(120, 100), (float("nan"), 100), (20, float("inf"))]:
            with self.subTest(actual=actual, projected=projected):
                self.assertIsNone(sleeper_win_percentage(actual, projected, 20, 100))

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
        rows, _ = player_data(data, "espn", "123", 2026, 2, 1)
        self.assertEqual(rows[0][9:], (12, 18, 24, 6))
        self.assertEqual(rows[1][9:], (None, None, None, None))


class SyncRecoveryTests(unittest.TestCase):
    def test_interrupted_download_retries_and_skips_complete_file(self):
        prefix = "provider=espn/league=123/season=2026/week=1/"
        blob = Mock(name="blob")
        blob.name = prefix + "team_snapshots/timestamp=1.pq"
        blob.size = 8

        def interrupted(path):
            Path(path).write_bytes(b"part")
            raise OSError("connection lost")

        with (
            tempfile.TemporaryDirectory() as directory,
            patch("google.cloud.storage.Client") as client,
        ):
            client.return_value.bucket.return_value.list_blobs.return_value = [blob]
            kwargs = dict(
                provider="espn",
                league_id="123",
                season=2026,
                matchup_period=1,
                output_dir=directory,
            )
            destination = Path(directory) / blob.name
            blob.download_to_filename.side_effect = interrupted
            with self.assertRaises(OSError):
                sync_parquet_prefix("test", **kwargs)
            self.assertFalse(destination.exists())
            self.assertEqual(list(Path(directory).rglob("*.part")), [])
            # A truncated file from an older sync must also be repaired.
            destination.write_bytes(b"part")
            blob.download_to_filename.side_effect = lambda path: Path(path).write_bytes(
                b"complete"
            )
            self.assertEqual(sync_parquet_prefix("test", **kwargs), 1)
            self.assertEqual(destination.read_bytes(), b"complete")
            blob.download_to_filename.reset_mock()
            self.assertEqual(sync_parquet_prefix("test", **kwargs), 0)
            blob.download_to_filename.assert_not_called()


class MetadataRecoveryTests(unittest.TestCase):
    def test_corrupt_state_recovers_and_destinations_are_independent(self):
        frames = {
            table: pd.DataFrame({"timestamp": [1], "name": ["Test"]})
            for table in ("league_metadata", "team_metadata", "player_metadata")
        }
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("fantasy_football.storage.pipeline.GCSObjectUploader"),
        ):
            writers = [
                build_writer(directory),
                build_writer(directory, "bucket-a"),
                build_writer(directory, "bucket-b"),
            ]
            self.assertEqual(len({writer.state_path for writer in writers}), 3)
            for writer in writers:
                writer.store = Mock()
                writer._write_changed_metadata(frames, "espn", "123", 2026, 1, 1)
                self.assertEqual(writer.store.write_frame.call_count, 3)
                writer._write_changed_metadata(frames, "espn", "123", 2026, 1, 2)
                self.assertEqual(writer.store.write_frame.call_count, 3)
            local = writers[0]
            state = local.state_path.with_name(f"{local.state_path.stem}_espn_123.json")
            state.write_text("{broken", encoding="utf-8")
            local._write_changed_metadata(frames, "espn", "123", 2026, 1, 3)
            self.assertEqual(local.store.write_frame.call_count, 6)
            local._write_changed_metadata(frames, "espn", "123", 2026, 1, 4)
            self.assertEqual(local.store.write_frame.call_count, 6)

    def test_failed_state_replace_preserves_previous_state(self):
        frames = {
            "league_metadata": pd.DataFrame({"timestamp": [1], "name": ["Old"]}),
            "team_metadata": pd.DataFrame(),
            "player_metadata": pd.DataFrame(),
        }
        with tempfile.TemporaryDirectory() as directory:
            writer = build_writer(directory)
            writer.store = Mock()
            writer._write_changed_metadata(frames, "espn", "123", 2026, 1, 1)
            state = writer.state_path.with_name(
                f"{writer.state_path.stem}_espn_123.json"
            )
            previous = state.read_bytes()
            frames["league_metadata"]["name"] = "New"
            with patch.object(Path, "replace", side_effect=OSError("interrupted")):
                with self.assertRaises(OSError):
                    writer._write_changed_metadata(frames, "espn", "123", 2026, 1, 2)
            self.assertEqual(state.read_bytes(), previous)
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])
            writer._write_changed_metadata(frames, "espn", "123", 2026, 1, 3)
            self.assertNotEqual(state.read_bytes(), previous)


if __name__ == "__main__":
    unittest.main()
