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
                patch("fantasy_football.cli._configured_writer") as writer,
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


class AllLeagueTests(unittest.TestCase):
    def config(self):
        from fantasy_football.config import LeagueConfig

        return LeagueConfig({"same": "1", "alias": "1"}, {"same": "2"})

    def test_all_sync_is_concurrent_and_deduplicates_ids(self):
        from threading import Barrier

        barrier = Barrier(2)

        def download(*args, **kwargs):
            barrier.wait(timeout=5)
            return 2

        with (
            patch("fantasy_football.cli.load_leagues", return_value=self.config()),
            patch(
                "fantasy_football.storage.sync.sync_parquet_prefix",
                side_effect=download,
            ) as sync,
        ):
            result = main(
                [
                    "sync",
                    "--all",
                    "--bucket",
                    "test",
                    "--season",
                    "2026",
                    "--week",
                    "1",
                    "--tables",
                    "team_snapshots",
                ]
            )
        self.assertEqual(result, 0)
        self.assertEqual(sync.call_count, 2)
        self.assertEqual(
            {call.kwargs["provider"] for call in sync.call_args_list},
            {"espn", "sleeper"},
        )
        self.assertTrue(
            all(
                call.kwargs["tables"] == ["team_snapshots"]
                for call in sync.call_args_list
            )
        )

    def test_provider_filter_and_sync_failure_status(self):
        with (
            patch("fantasy_football.cli.load_leagues", return_value=self.config()),
            patch(
                "fantasy_football.storage.sync.sync_parquet_prefix",
                side_effect=OSError("offline"),
            ) as sync,
        ):
            result = main(
                [
                    "sync",
                    "--all",
                    "--provider",
                    "sleeper",
                    "--bucket",
                    "test",
                    "--season",
                    "2026",
                    "--week",
                    "1",
                ]
            )
        self.assertEqual(result, 1)
        self.assertEqual(sync.call_count, 1)
        self.assertEqual(sync.call_args.kwargs["league_id"], "2")

    def test_single_sync_still_works_without_config(self):
        with (
            patch("fantasy_football.cli.load_leagues") as config,
            patch("fantasy_football.storage.sync.sync_parquet_prefix", return_value=0),
        ):
            self.assertEqual(
                main(
                    [
                        "sync",
                        "--provider",
                        "espn",
                        "--league-id",
                        "1",
                        "--bucket",
                        "test",
                        "--season",
                        "2026",
                        "--week",
                        "1",
                    ]
                ),
                0,
            )
            config.assert_not_called()

    def test_all_plot_paths_include_provider(self):
        import pandas as pd

        with (
            patch("fantasy_football.cli.load_leagues", return_value=self.config()),
            patch(
                "fantasy_football.storage.duckdb.load_matchup_results",
                return_value=pd.DataFrame(),
            ),
            patch(
                "fantasy_football.plotting.generate_matchup_plots",
                return_value=[Path("test.png")],
            ) as plot,
        ):
            self.assertEqual(
                main(["analyze", "--all", "--season", "2026", "--week", "1"]), 0
            )
        paths = [call.kwargs["output_dir"] for call in plot.call_args_list]
        self.assertEqual(len(set(paths)), 2)
        self.assertTrue(any("espn" in path.parts for path in paths))
        self.assertTrue(any("sleeper" in path.parts for path in paths))

    def test_all_plot_skips_absent_leagues(self):
        import pandas as pd

        with (
            patch("fantasy_football.cli.load_leagues", return_value=self.config()),
            patch(
                "fantasy_football.storage.duckdb.load_matchup_results",
                side_effect=[FileNotFoundError(), pd.DataFrame()],
            ),
            patch(
                "fantasy_football.plotting.generate_matchup_plots",
                return_value=[Path("test.png")],
            ),
        ):
            self.assertEqual(
                main(["analyze", "--all", "--season", "2026", "--week", "1"]), 0
            )

    def test_conflicting_selection_is_rejected(self):
        for command in (
            [
                "sync",
                "--all",
                "--league-id",
                "1",
                "--bucket",
                "test",
                "--season",
                "2026",
                "--week",
                "1",
            ],
            ["analyze", "--all", "--league", "same", "--season", "2026", "--week", "1"],
            [
                "sync",
                "--league-id",
                "1",
                "--bucket",
                "test",
                "--season",
                "2026",
                "--week",
                "1",
            ],
        ):
            with (
                self.subTest(command=command),
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit) as error,
            ):
                main(command)
            self.assertEqual(error.exception.code, 2)
