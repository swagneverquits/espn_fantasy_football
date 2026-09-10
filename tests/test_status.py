import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from rich.console import Console

from fantasy_football.config import LeagueConfig
from fantasy_football.runner import Poller
from fantasy_football.status import WorkerStatus, read_status, status_table


class StatusTests(unittest.TestCase):
    def test_success_only_after_write_and_failure_preserves_last_success(self):
        with tempfile.TemporaryDirectory() as directory:
            status = WorkerStatus("espn", "1", Path(directory))
            writer = Mock()
            writer.write.return_value = 12
            poller = Poller(Mock(), writer, status)
            with status:
                self.assertEqual(poller.scrape_once(), 12)
                successful = read_status(status.path)
                self.assertEqual(successful["last_result"], "Success")
                writer.write.side_effect = OSError("upload failed")
                with self.assertRaises(OSError):
                    poller.scrape_once()
                failed = read_status(status.path)
                self.assertEqual(failed["last_result"], "Failed")
                self.assertEqual(failed["last_success"], successful["last_success"])
                self.assertEqual(failed["errors"], 1)
            self.assertEqual(read_status(status.path)["status"], "Stopped")
            self.assertFalse(status.thread.is_alive())
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])

    def test_missing_corrupt_and_stale_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            status = WorkerStatus("espn", "1", root)
            status.update(status="Idle")
            with patch("fantasy_football.status.time.time", return_value=1e12):
                output = io.StringIO()
                Console(file=output, width=160).print(
                    status_table(LeagueConfig({"one": "1"}, {"two": "2"}), root)
                )
            self.assertIn("Stale / offline", output.getvalue())
            self.assertIn("Not running", output.getvalue())
            status.path.write_text("broken", encoding="utf-8")
            self.assertEqual(read_status(status.path), {})

    def test_monitoring_write_failure_does_not_stop_scrape(self):
        with tempfile.TemporaryDirectory() as directory:
            status = WorkerStatus("espn", "1", Path(directory))
            with patch(
                "fantasy_football.status.tempfile.NamedTemporaryFile",
                side_effect=OSError("disk full"),
            ):
                status.update(status="Scraping")

    def test_cli_status_dispatch(self):
        from fantasy_football.cli import main

        with (
            patch("fantasy_football.cli.load_leagues") as config,
            patch("fantasy_football.status.show_status", return_value=0) as show,
        ):
            self.assertEqual(main(["status", "--watch"]), 0)
            show.assert_called_once_with(config.return_value, watch=True)
