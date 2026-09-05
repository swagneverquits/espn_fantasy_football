import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fantasy_football.storage.sync import sync_parquet_prefix


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
