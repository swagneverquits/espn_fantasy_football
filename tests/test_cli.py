"""CLI imports and argument parsing must not require local league configuration."""

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fantasy_football.cli import main
from fantasy_football.config import load_leagues


class ConfigTests(unittest.TestCase):
    def test_explicit_config_loading_and_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "leagues.toml"
            with self.assertRaises(FileNotFoundError):
                load_leagues(path)
            path.write_text("[espn]\nexample = 123\n[sleeper]\nother = 456\n")
            config = load_leagues(path)
            self.assertEqual(config.league_id("espn", "example"), "123")
            self.assertEqual(config.league_id("sleeper", "other"), "456")
            self.assertEqual(config.path, path.resolve())
            with self.assertRaises(ValueError):
                config.league_id("espn", "unknown")

    def test_help_does_not_load_configuration(self):
        for command in (
            [],
            ["scrape", "espn"],
            ["scrape", "all"],
            ["analyze"],
            ["sync"],
        ):
            with (
                self.subTest(command=command),
                patch("fantasy_football.cli.load_leagues") as load,
            ):
                with (
                    contextlib.redirect_stdout(io.StringIO()),
                    self.assertRaises(SystemExit) as exit,
                ):
                    main(["--config", "missing.toml", *command, "--help"])
                self.assertEqual(exit.exception.code, 0)
                load.assert_not_called()

    def test_cli_import_does_not_load_plotting_or_duckdb(self):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; import fantasy_football.cli; "
                "assert 'matplotlib' not in sys.modules; assert 'duckdb' not in sys.modules",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_single_scrape_wires_explicit_config_and_storage(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "leagues.toml"
            path.write_text("[espn]\nexample = 123\n")
            with (
                patch("fantasy_football.scrapers.espn.scraper.ESPNScraper") as scraper,
                patch("fantasy_football.storage.pipeline.configured_writer") as writer,
                patch("fantasy_football.runner.Poller") as poller,
            ):
                result = main(
                    [
                        "--config",
                        str(path),
                        "scrape",
                        "espn",
                        "--league",
                        "example",
                        "--once",
                        "--storage",
                        "gcs",
                        "--interval",
                        "45",
                    ]
                )
            self.assertEqual(result, 0)
            scraper.assert_called_once_with("123", season=2026)
            writer.assert_called_once_with("gcs")
            poller.assert_called_once_with(scraper.return_value, writer.return_value)
            poller.return_value.run.assert_called_once_with(
                interval_seconds=45,
                retry_seconds=30,
                once=True,
                schedule_gate=True,
            )
