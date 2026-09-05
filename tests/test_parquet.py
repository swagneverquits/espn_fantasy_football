"""Local publishing must be atomic even when source and output use different volumes."""

import errno
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fantasy_football.storage.parquet import LocalObjectUploader


class LocalPublishingTests(unittest.TestCase):
    def test_rename_only_occurs_within_destination_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pq"
            source.write_bytes(b"complete")
            destination = root / "output" / "table" / "snapshot.pq"
            original_replace = Path.replace

            def same_filesystem_only(path, target):
                if path.parent != Path(target).parent:
                    raise OSError(errno.EXDEV, "Cross-device link")
                return original_replace(path, target)

            with patch.object(Path, "replace", same_filesystem_only):
                LocalObjectUploader(root / "output").upload(source, "table/snapshot.pq")
            self.assertEqual(destination.read_bytes(), b"complete")
            self.assertEqual(source.read_bytes(), b"complete")
            self.assertEqual(list(destination.parent.glob("*.tmp")), [])

    def test_interrupted_copy_preserves_previous_object(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pq"
            source.write_bytes(b"new")
            destination = root / "output" / "snapshot.pq"
            destination.parent.mkdir()
            destination.write_bytes(b"previous")

            def interrupted_copy(source, target):
                Path(target).write_bytes(b"partial")
                raise OSError("copy interrupted")

            with patch(
                "fantasy_football.storage.parquet.shutil.copyfile",
                side_effect=interrupted_copy,
            ):
                with self.assertRaises(OSError):
                    LocalObjectUploader(destination.parent).upload(
                        source, destination.name
                    )
            self.assertEqual(destination.read_bytes(), b"previous")
            self.assertEqual(list(destination.parent.glob("*.tmp")), [])
