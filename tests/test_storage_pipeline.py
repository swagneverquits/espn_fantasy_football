import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd

from fantasy_football.snapshot import Snapshot
from fantasy_football.storage.duckdb import load_matchup_results
from fantasy_football.storage.pipeline import build_writer


class ParquetPipelineTests(unittest.TestCase):
    def test_round_trip_and_change_only_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            writer = build_writer(root)

            def snapshot(timestamp):
                return Snapshot.from_records(
                    provider="espn",
                    league_id="123",
                    season=2026,
                    matchup_period=1,
                    timestamp=timestamp,
                    league_name="Test League",
                    team_snapshots=[
                        {
                            "team_id": 1,
                            "matchup_id": 1,
                            "opponent_id": 2,
                            "score_live": 20,
                            "projected_live": 100,
                            "win_probability": 0.6,
                        },
                        {
                            "team_id": 2,
                            "matchup_id": 1,
                            "opponent_id": 1,
                            "score_live": 18,
                            "projected_live": 95,
                            "win_probability": 0.4,
                        },
                    ],
                    team_metadata=[
                        {"team_id": 1, "team_name": "A", "logo_url": "a"},
                        {"team_id": 2, "team_name": "B", "logo_url": "b"},
                    ],
                    player_snapshots=[],
                    player_metadata=[],
                )

            writer.write(snapshot(1788372000))
            first_files = list(root.rglob("*.pq"))
            writer.write(snapshot(1788372030))
            result = load_matchup_results(
                root, provider="espn", league_id="123", season=2026, matchup_period=1
            )
            self.assertEqual(len(first_files), 4)
            self.assertEqual(len(list(root.rglob("*.pq"))), 6)
            self.assertEqual(len(result), 4)
            self.assertEqual(result["league_name"].iloc[0], "Test League")
            self.assertEqual(result["team_id"].tolist(), [1, 2, 1, 2])
            self.assertEqual(
                result["timestamp"].tolist(),
                [1788372000, 1788372000, 1788372030, 1788372030],
            )
            self.assertIn("score_live", result)
            # The original persisted schema is still readable without aliases.
            stored = pd.read_parquet(first_files[0])
            self.assertIn("timestamp", stored)


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
