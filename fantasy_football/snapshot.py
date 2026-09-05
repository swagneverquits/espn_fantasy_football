"""The common five-table contract shared by providers and storage."""

from dataclasses import dataclass
from typing import Any

import pandas as pd

from fantasy_football.constants import (
    COMMON_INDEX_COLS,
    MATCHUP_ID_COL,
    MATCHUP_PERIOD_COL,
    TEAM_ID_COL,
    TIMESTAMP_COL,
)

IDENTITY = COMMON_INDEX_COLS
WEEK_IDENTITY = (*IDENTITY, MATCHUP_PERIOD_COL)
SCHEMAS = {
    "team_snapshots": (
        *WEEK_IDENTITY,
        MATCHUP_ID_COL,
        TIMESTAMP_COL,
        TEAM_ID_COL,
        "opponent_id",
        "score_live",
        "projected_live",
        "win_probability",
    ),
    "player_snapshots": (
        *WEEK_IDENTITY,
        MATCHUP_ID_COL,
        TIMESTAMP_COL,
        TEAM_ID_COL,
        "player_id",
        "lineup_slot_id",
        "points_live",
        "projected",
        "ceiling",
        "projection_spread",
    ),
    "team_metadata": (
        *WEEK_IDENTITY,
        TEAM_ID_COL,
        "team_name",
        "logo_url",
        TIMESTAMP_COL,
    ),
    "league_metadata": (*IDENTITY, "league_name", TIMESTAMP_COL),
    "player_metadata": (
        *WEEK_IDENTITY,
        "player_id",
        TIMESTAMP_COL,
        "player_name",
        "position",
    ),
}


@dataclass(frozen=True)
class Snapshot:
    """Normalized tables plus partition identity for a single poll."""

    provider: str
    league_id: str
    season: int
    matchup_period: int
    timestamp: int
    team_snapshots: pd.DataFrame
    player_snapshots: pd.DataFrame
    team_metadata: pd.DataFrame
    league_metadata: pd.DataFrame
    player_metadata: pd.DataFrame

    @property
    def frames(self) -> dict[str, pd.DataFrame]:
        return {table: getattr(self, table) for table in SCHEMAS}

    @classmethod
    def from_records(
        cls,
        *,
        provider: str,
        league_id: str | int,
        season: int,
        matchup_period: int,
        timestamp: int,
        league_name: str | None,
        team_snapshots: list[dict[str, Any]],
        team_metadata: list[dict[str, Any]],
        player_snapshots: list[tuple],
        player_metadata: list[tuple],
    ) -> "Snapshot":
        """Apply the schema to already normalized provider records."""
        identity = dict(
            zip(WEEK_IDENTITY, (provider, str(league_id), season, matchup_period))
        )
        identity[TIMESTAMP_COL] = timestamp
        records = {
            "team_snapshots": [{**identity, **row} for row in team_snapshots],
            "team_metadata": [{**identity, **row} for row in team_metadata],
            "league_metadata": [{**identity, "league_name": league_name}],
            "player_snapshots": player_snapshots,
            "player_metadata": player_metadata,
        }
        frames = {
            table: pd.DataFrame(rows, columns=SCHEMAS[table])
            for table, rows in records.items()
        }
        frames["team_snapshots"]["projected_live"] = pd.to_numeric(
            frames["team_snapshots"]["projected_live"], errors="coerce"
        ).round(2)
        return cls(
            provider, str(league_id), season, matchup_period, timestamp, **frames
        )
