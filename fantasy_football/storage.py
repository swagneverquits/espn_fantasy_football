"""Shared SQLite storage and CSV export for all fantasy providers."""

import json
import sqlite3
from pathlib import Path

import pandas as pd

from fantasy_football.constants import (
    COMMON_INDEX_COLS,
    LEAGUE_ID_COL,
    LEAGUE_METADATA_TABLE,
    MATCHUP_ID_COL,
    MATCHUP_PERIOD_COL,
    PLAYER_METADATA_TABLE,
    PLAYER_SNAPSHOTS_TABLE,
    PROVIDER_COL,
    SEASON_COL,
    SQLITE_PATH,
    TEAM_ID_COL,
    TEAM_METADATA_TABLE,
    TEAM_SNAPSHOTS_TABLE,
    TIMESTAMP_COL,
)


def _schema(connection):
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS team_snapshots (
            provider TEXT NOT NULL,
            league_id TEXT NOT NULL,
            season INTEGER NOT NULL,
            matchup_period INTEGER NOT NULL,
            matchup_id INTEGER,
            timestamp INTEGER NOT NULL,
            team_id INTEGER NOT NULL,
            opponent_id INTEGER,
            score_live REAL,
            projected_live REAL,
            win_probability REAL
        );
        CREATE TABLE IF NOT EXISTS player_snapshots (
            provider TEXT NOT NULL,
            league_id TEXT NOT NULL,
            season INTEGER NOT NULL,
            matchup_period INTEGER NOT NULL,
            matchup_id INTEGER,
            timestamp INTEGER NOT NULL,
            team_id INTEGER NOT NULL,
            player_id INTEGER NOT NULL,
            lineup_slot_id TEXT,
            points_live REAL,
            projected REAL,
            ceiling REAL,
            projection_spread REAL
        );
        CREATE TABLE IF NOT EXISTS team_metadata (
            provider TEXT NOT NULL,
            league_id TEXT NOT NULL,
            season INTEGER NOT NULL,
            matchup_period INTEGER NOT NULL,
            team_id INTEGER NOT NULL,
            team_name TEXT,
            logo_url TEXT,
            timestamp INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS league_metadata (
            provider TEXT NOT NULL,
            league_id TEXT NOT NULL,
            season INTEGER NOT NULL,
            league_name TEXT,
            timestamp INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS player_metadata (
            provider TEXT NOT NULL,
            league_id TEXT NOT NULL,
            season INTEGER NOT NULL,
            matchup_period INTEGER NOT NULL,
            player_id INTEGER NOT NULL,
            timestamp INTEGER NOT NULL,
            player_name TEXT,
            position TEXT
        );
        """)


def _unix_seconds(value):
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    return int(timestamp.timestamp())


def _sleeper_projection_key(settings):
    rec = (settings or {}).get("rec")
    if rec == 1:
        return "pts_ppr"
    if rec == 0.5:
        return "pts_half_ppr"
    return "pts_std"


def _espn_position(position_id):
    return position_id


def _espn_player_data(data, league_id, season, week, timestamp):
    snapshots = []
    metadata = {}
    for matchup in data.get("schedule", []):
        if matchup.get("matchupPeriodId") != week:
            continue
        for side in ("away", "home"):
            team = matchup.get(side) or {}
            roster = team.get("rosterForCurrentScoringPeriod") or {}
            for entry in roster.get("entries", []):
                player = (entry.get("playerPoolEntry") or {}).get("player") or {}
                player_id = player.get("id")
                if player_id is None:
                    continue

                stats = player.get("stats") or []
                current = next(
                    (
                        stat
                        for stat in stats
                        if stat.get("scoringPeriodId") == week
                        and stat.get("statSourceId") == 1
                    ),
                    stats[0] if stats else {},
                )
                projected = current.get("appliedTotal")
                ceiling = current.get("appliedTotalCeiling")
                spread = (
                    ceiling - projected
                    if ceiling is not None and projected is not None
                    else None
                )
                snapshots.append(
                    (
                        "espn",
                        str(league_id),
                        season,
                        week,
                        matchup.get("id"),
                        timestamp,
                        team.get("teamId"),
                        player_id,
                        entry.get("lineupSlotId"),
                        None,
                        projected,
                        ceiling,
                        spread,
                    )
                )
                metadata[player_id] = (
                    "espn",
                    str(league_id),
                    season,
                    week,
                    player_id,
                    timestamp,
                    player.get("fullName"),
                    _espn_position(player.get("defaultPositionId")),
                )
    return snapshots, list(metadata.values())


def _sleeper_player_data(data, league_id, season, week, timestamp):
    snapshots = []
    metadata = {}
    league = data.get("league", {})
    scoring_key = _sleeper_projection_key(league.get("scoring_settings"))
    player_data = data.get("player_data", {})
    projections = {
        str(player.get("player_id")): player
        for player in player_data.get("projections", [])
    }
    stats = {
        str(player.get("player_id")): player for player in player_data.get("stats", [])
    }

    for matchup in data.get("matchups", []):
        for slot, player_id in enumerate(matchup.get("starters") or []):
            player_key = str(player_id)
            projection = projections.get(player_key, {})
            projected = (projection.get("stats") or {}).get(scoring_key)
            if projected is None or not player_key.isdigit():
                continue

            player = projection.get("player") or {}
            actual = (stats.get(player_key, {}).get("stats") or {}).get(scoring_key)
            numeric_id = int(player_key)
            snapshots.append(
                (
                    "sleeper",
                    str(league_id),
                    season,
                    week,
                    matchup.get(MATCHUP_ID_COL),
                    timestamp,
                    matchup.get("roster_id"),
                    numeric_id,
                    slot,
                    actual,
                    projected,
                    None,
                    None,
                )
            )
            metadata[numeric_id] = (
                "sleeper",
                str(league_id),
                season,
                week,
                numeric_id,
                timestamp,
                " ".join(
                    filter(None, [player.get("first_name"), player.get("last_name")])
                ),
                player.get("position"),
            )
    return snapshots, list(metadata.values())


def _player_data(data, provider, league_id, season, week, timestamp):
    if provider == "espn":
        return _espn_player_data(data, league_id, season, week, timestamp)
    return _sleeper_player_data(data, league_id, season, week, timestamp)


def _append_changed(connection, table, frame, key_columns):
    """Append metadata rows only when the weekly value is new or changed."""
    if frame.empty:
        return
    existing = pd.read_sql_query(f"SELECT * FROM {table}", connection)
    if existing.empty:
        frame.to_sql(table, connection, if_exists="append", index=False)
        return
    compare_columns = [column for column in frame.columns if column != TIMESTAMP_COL]
    changed = []
    for row in frame.to_dict("records"):
        mask = pd.Series(True, index=existing.index)
        for column in key_columns:
            mask &= existing[column].eq(row[column])
        matches = existing.loc[mask]
        if matches.empty:
            changed.append(row)
            continue
        previous = matches.iloc[-1]
        if any(
            not (pd.isna(row[column]) and pd.isna(previous[column]))
            and row[column] != previous[column]
            for column in compare_columns
        ):
            changed.append(row)
    if changed:
        pd.DataFrame(changed, columns=frame.columns).to_sql(
            table, connection, if_exists="append", index=False
        )


def write_sqlite_snapshot(
    frame, *, provider, league_id, season, matchup_period, data=None, path=SQLITE_PATH
):
    """Append one poll to shared team, player, and metadata tables."""
    output = frame.reset_index()
    if output.empty:
        if data is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            poll_timestamp = int(pd.Timestamp.now(tz="UTC").timestamp())
            with sqlite3.connect(path) as connection:
                _schema(connection)
                league_name = (data.get("league") or {}).get("name") or data.get("name")
                if provider == "espn":
                    league_name = (data.get("settings") or {}).get(
                        "name"
                    ) or league_name
                league_metadata = pd.DataFrame(
                    [(provider, str(league_id), season, league_name, poll_timestamp)],
                    columns=[
                        PROVIDER_COL,
                        LEAGUE_ID_COL,
                        SEASON_COL,
                        "league_name",
                        TIMESTAMP_COL,
                    ],
                )
                _append_changed(
                    connection,
                    LEAGUE_METADATA_TABLE,
                    league_metadata,
                    [*COMMON_INDEX_COLS],
                )
        return 0
    timestamp = output["time"].map(_unix_seconds)
    poll_timestamp = int(timestamp.iloc[0])
    team_rows = pd.DataFrame(
        {
            PROVIDER_COL: provider,
            LEAGUE_ID_COL: str(league_id),
            SEASON_COL: season,
            MATCHUP_PERIOD_COL: matchup_period,
            TIMESTAMP_COL: timestamp,
            MATCHUP_ID_COL: output["Matchup"],
            TEAM_ID_COL: output[TEAM_ID_COL],
            "opponent_id": output["opponent_id"],
            "score_live": output["TotalPointsLive"],
            "projected_live": output["Projected"].round(2),
            "win_probability": output["WinChance"],
        }
    )
    team_rows = team_rows[
        [
            PROVIDER_COL,
            LEAGUE_ID_COL,
            SEASON_COL,
            MATCHUP_PERIOD_COL,
            MATCHUP_ID_COL,
            TIMESTAMP_COL,
            TEAM_ID_COL,
            "opponent_id",
            "score_live",
            "projected_live",
            "win_probability",
        ]
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        _schema(connection)
        team_rows.to_sql(
            TEAM_SNAPSHOTS_TABLE, connection, if_exists="append", index=False
        )
        if data is None:
            return len(team_rows)
        player_rows, player_meta = _player_data(
            data, provider, league_id, season, matchup_period, poll_timestamp
        )
        pd.DataFrame(
            player_rows,
            columns=[
                PROVIDER_COL,
                LEAGUE_ID_COL,
                SEASON_COL,
                MATCHUP_PERIOD_COL,
                MATCHUP_ID_COL,
                TIMESTAMP_COL,
                TEAM_ID_COL,
                "player_id",
                "lineup_slot_id",
                "points_live",
                "projected",
                "ceiling",
                "projection_spread",
            ],
        ).to_sql(PLAYER_SNAPSHOTS_TABLE, connection, if_exists="append", index=False)
        if provider == "espn":
            team_meta = []
            for team in data.get("teams", []):
                team_meta.append(
                    (
                        provider,
                        str(league_id),
                        season,
                        matchup_period,
                        team.get("id"),
                        team.get("name"),
                        team.get("logo"),
                        poll_timestamp,
                    )
                )
        else:
            users = {str(u.get("user_id")): u for u in data.get("users", [])}
            team_meta = []
            for roster in data.get("rosters", []):
                user = users.get(str(roster.get("owner_id")), {})
                meta = user.get("metadata") or {}
                team_meta.append(
                    (
                        provider,
                        str(league_id),
                        season,
                        matchup_period,
                        roster.get("roster_id"),
                        meta.get("team_name") or user.get("display_name"),
                        meta.get("avatar") or user.get("avatar"),
                        poll_timestamp,
                    )
                )
        team_metadata = pd.DataFrame(
            team_meta,
            columns=[
                PROVIDER_COL,
                LEAGUE_ID_COL,
                SEASON_COL,
                MATCHUP_PERIOD_COL,
                TEAM_ID_COL,
                "team_name",
                "logo_url",
                TIMESTAMP_COL,
            ],
        )
        _append_changed(
            connection,
            TEAM_METADATA_TABLE,
            team_metadata,
            [*COMMON_INDEX_COLS, MATCHUP_PERIOD_COL, TEAM_ID_COL],
        )
        league_name = (data.get("league") or {}).get("name") or data.get("name")
        if provider == "espn":
            league_name = (data.get("settings") or {}).get("name") or league_name
        league_metadata = pd.DataFrame(
            [(provider, str(league_id), season, league_name, poll_timestamp)],
            columns=[
                PROVIDER_COL,
                LEAGUE_ID_COL,
                SEASON_COL,
                "league_name",
                TIMESTAMP_COL,
            ],
        )
        _append_changed(
            connection,
            LEAGUE_METADATA_TABLE,
            league_metadata,
            [*COMMON_INDEX_COLS],
        )
        player_metadata = pd.DataFrame(
            player_meta,
            columns=[
                PROVIDER_COL,
                LEAGUE_ID_COL,
                SEASON_COL,
                MATCHUP_PERIOD_COL,
                "player_id",
                TIMESTAMP_COL,
                "player_name",
                "position",
            ],
        )
        _append_changed(
            connection,
            PLAYER_METADATA_TABLE,
            player_metadata,
            [*COMMON_INDEX_COLS, MATCHUP_PERIOD_COL, "player_id"],
        )
    return len(team_rows)


def load_matchup_results(
    source: str | Path = SQLITE_PATH,
    *,
    provider: str,
    league_id: str | int,
    season: int,
    matchup_period: int,
) -> pd.DataFrame:
    """Load normalized matchup rows from the canonical SQLite database."""
    source = Path(source)
    if not source.exists():
        raise FileNotFoundError(f"SQLite database not found: {source}")

    query = f"""
        WITH latest_team_metadata AS (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY provider, league_id, season, matchup_period, team_id
                ORDER BY timestamp DESC
            ) AS row_number
            FROM {TEAM_METADATA_TABLE}
        ), latest_league_metadata AS (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY provider, league_id, season
                ORDER BY timestamp DESC
            ) AS row_number
            FROM {LEAGUE_METADATA_TABLE}
        )
        SELECT
            snapshots.timestamp AS time,
            COALESCE(team_metadata.team_name, CAST(snapshots.team_id AS TEXT)) AS team,
            snapshots.matchup_id AS Matchup,
            snapshots.matchup_period AS MatchupPeriod,
            snapshots.score_live AS Score,
            snapshots.projected_live AS Projected,
            snapshots.win_probability AS WinChance,
            league_metadata.league_name AS league_name
        FROM {TEAM_SNAPSHOTS_TABLE} AS snapshots
        LEFT JOIN latest_team_metadata AS team_metadata
            ON team_metadata.provider = snapshots.provider
            AND team_metadata.league_id = snapshots.league_id
            AND team_metadata.season = snapshots.season
            AND team_metadata.matchup_period = snapshots.matchup_period
            AND team_metadata.team_id = snapshots.team_id
            AND team_metadata.row_number = 1
        LEFT JOIN latest_league_metadata AS league_metadata
            ON league_metadata.provider = snapshots.provider
            AND league_metadata.league_id = snapshots.league_id
            AND league_metadata.season = snapshots.season
            AND league_metadata.row_number = 1
        WHERE snapshots.provider = ?
            AND snapshots.league_id = ?
            AND snapshots.season = ?
            AND snapshots.matchup_period = ?
        ORDER BY snapshots.timestamp, snapshots.matchup_id, snapshots.team_id
    """
    with sqlite3.connect(source) as connection:
        frame = pd.read_sql_query(
            query,
            connection,
            params=(provider, str(league_id), season, matchup_period),
        )
    if frame.empty:
        raise ValueError(
            f"No matchup snapshots found for {provider}/{league_id}, "
            f"season {season}, week {matchup_period}"
        )

    frame["time"] = pd.to_datetime(frame["time"], unit="s", utc=True).dt.tz_convert(
        "America/New_York"
    )
    return frame.set_index(["time", "team"])


def export_sqlite_csvs(source, output_dir):
    """Export SQLite tables with UTC epoch timestamps rendered in ET to seconds."""
    source = Path(source)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    tables = (
        LEAGUE_METADATA_TABLE,
        TEAM_SNAPSHOTS_TABLE,
        PLAYER_SNAPSHOTS_TABLE,
        TEAM_METADATA_TABLE,
        PLAYER_METADATA_TABLE,
    )
    with sqlite3.connect(source) as connection:
        for table in tables:
            frame = pd.read_sql_query(f"SELECT * FROM {table}", connection)
            if TIMESTAMP_COL in frame.columns and not frame.empty:
                frame[TIMESTAMP_COL] = (
                    pd.to_datetime(frame[TIMESTAMP_COL], unit="s", utc=True)
                    .dt.tz_convert("America/New_York")
                    .dt.strftime("%Y-%m-%d %H:%M:%S")
                )
            frame.to_csv(output_dir / f"{table}.csv", index=False)
