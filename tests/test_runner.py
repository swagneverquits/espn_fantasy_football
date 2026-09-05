import unittest
from unittest.mock import Mock, patch

from fantasy_football.config import LeagueConfig
from fantasy_football.runner import Poller, RunOptions, run_all


class WorkerTests(unittest.TestCase):
    def test_once_waits_for_all_successful_workers(self):
        first, second = Mock(), Mock()
        first.poll.return_value = 0
        second.poll.side_effect = [None, 0]
        with (
            patch(
                "fantasy_football.runner.subprocess.Popen", side_effect=[first, second]
            ) as spawn,
            patch("fantasy_football.runner.time.sleep"),
        ):
            result = run_all(
                LeagueConfig({"a": "1"}, {"b": "2"}), RunOptions(once=True)
            )
        self.assertEqual(result, 0)
        second.terminate.assert_not_called()
        self.assertTrue(all("--once" in call.args[0] for call in spawn.call_args_list))
        self.assertIn("sleeper", spawn.call_args_list[1].args[0])

    def test_failed_worker_stops_remaining_workers(self):
        for once in (False, True):
            with self.subTest(once=once):
                first, second = Mock(), Mock()
                first.poll.return_value = 2
                second.poll.return_value = None
                with patch(
                    "fantasy_football.runner.subprocess.Popen",
                    side_effect=[first, second],
                ):
                    result = run_all(
                        LeagueConfig({"a": "1", "b": "2"}, {}), RunOptions(once=once)
                    )
                self.assertEqual(result, 2)
                second.terminate.assert_called_once()

    def test_poller_once_bypasses_schedule_and_persists_snapshot(self):
        scraper, writer = Mock(), Mock()
        writer.write.return_value = 2
        with patch("fantasy_football.runner.get_game_starts") as schedule:
            self.assertEqual(Poller(scraper, writer).run(once=True), 2)
        schedule.assert_not_called()
        writer.write.assert_called_once_with(scraper.fetch_snapshot.return_value)

    def test_one_shot_failure_propagates(self):
        scraper = Mock()
        scraper.fetch_snapshot.side_effect = OSError("provider down")
        with self.assertRaises(OSError):
            Poller(scraper, Mock()).run(once=True)
