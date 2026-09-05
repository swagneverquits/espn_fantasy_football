"""DuckDB-backed local queries over raw Parquet snapshot objects."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from fantasy_football.constants import TEAM_ID_COL, TIMESTAMP_COL


def _sql_path(path: Path) -> str:
    """Render a local path as a safely quoted DuckDB string literal."""
    return "'" + path.as_posix().replace("'", "''") + "'"


def _parquet_glob(prefix: Path, table: str) -> Path:
    return prefix / table / "*.pq"


def load_matchup_results(
    root: str | Path,
    *,
    provider: str,
    league_id: str | int,
    season: int,
    matchup_period: int,
) -> pd.DataFrame:
    """Query raw local Parquet snapshots and return the plotting DataFrame."""
    prefix = (
        Path(root)
        / f"provider={provider}"
        / f"league={league_id}"
        / f"season={season}"
        / f"week={matchup_period}"
    )
    snapshot_glob = _parquet_glob(prefix, "team_snapshots")
    if not list(snapshot_glob.parent.glob(snapshot_glob.name)):
        raise FileNotFoundError(f"No Parquet snapshots found under {prefix}")

    team_glob = _parquet_glob(prefix, "team_metadata")
    league_glob = _parquet_glob(prefix, "league_metadata")
    team_join = ""
    team_name = "CAST(s.team_id AS VARCHAR)"
    if list(team_glob.parent.glob(team_glob.name)):
        team_join = f"""
        LEFT JOIN (
            SELECT {TEAM_ID_COL},
                   arg_max(team_name, {TIMESTAMP_COL}) AS team_name
            FROM read_parquet({_sql_path(team_glob)}, union_by_name=true)
            GROUP BY {TEAM_ID_COL}
        ) AS t USING ({TEAM_ID_COL})
        """
        team_name = "COALESCE(t.team_name, CAST(s.team_id AS VARCHAR))"

    league_name = "NULL::VARCHAR"
    if list(league_glob.parent.glob(league_glob.name)):
        league_name = f"""(
            SELECT arg_max(league_name, {TIMESTAMP_COL})
            FROM read_parquet({_sql_path(league_glob)}, union_by_name=true)
        )"""

    query = f"""
        SELECT
            s.*,
            {team_name} AS team_name,
            {league_name} AS league_name
        FROM read_parquet({_sql_path(snapshot_glob)}, union_by_name=true) AS s
        {team_join}
        ORDER BY s.{TIMESTAMP_COL}, s.matchup_id, s.{TEAM_ID_COL}
    """
    with duckdb.connect() as connection:
        result = connection.sql(query).fetchdf()

    return result
