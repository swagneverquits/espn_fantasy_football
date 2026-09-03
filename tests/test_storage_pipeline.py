import tempfile
import unittest
from pathlib import Path

import pandas as pd

from fantasy_football.storage.pipeline import (
    build_writer,
    load_matchup_results_from_parquet,
)


class ParquetPipelineTests(unittest.TestCase):
    def test_round_trip_and_change_only_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            writer = build_writer(root)
            data = {
                "teams": [
                    {"id": 1, "name": "A", "logo": "a"},
                    {"id": 2, "name": "B", "logo": "b"},
                ],
                "schedule": [],
                "settings": {"name": "Test League"},
            }

            def frame(timestamp):
                index = pd.MultiIndex.from_tuples(
                    [(timestamp, "A"), (timestamp, "B")],
                    names=["time", "team"],
                )
                return pd.DataFrame(
                    {
                        "team_id": [1, 2],
                        "opponent_id": [2, 1],
                        "Matchup": [1, 1],
                        "TotalPointsLive": [20.0, 18.0],
                        "Projected": [100.0, 95.0],
                        "WinChance": [0.6, 0.4],
                    },
                    index=index,
                )

            writer.write(
                frame(pd.Timestamp("2026-09-02T18:00:00Z")),
                provider="espn",
                league_id=123,
                season=2026,
                matchup_period=1,
                data=data,
            )
            first_files = list(root.rglob("*.pq"))
            writer.write(
                frame(pd.Timestamp("2026-09-02T18:00:30Z")),
                provider="espn",
                league_id=123,
                season=2026,
                matchup_period=1,
                data=data,
            )
            second_files = list(root.rglob("*.pq"))

            result = load_matchup_results_from_parquet(
                root,
                provider="espn",
                league_id=123,
                season=2026,
                matchup_period=1,
            )
            self.assertEqual(len(first_files), 4)
            self.assertEqual(len(second_files), 6)
            self.assertEqual(len(result), 4)
            self.assertEqual(result["league_name"].iloc[0], "Test League")


if __name__ == "__main__":
    unittest.main()
