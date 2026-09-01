"""Shared CSV and four-table SQLite storage for all fantasy providers."""

import json
import sqlite3
from pathlib import Path

import pandas as pd

DEFAULT_INTERVAL_SECONDS = 30
DEFAULT_RETRY_SECONDS = 30
SQLITE_PATH = Path(__file__).resolve().parent.parent / "data" / "fantasy_football.sqlite"


def write_snapshot(path: Path, frame: pd.DataFrame) -> int:
    """Append a standardized snapshot frame to a CSV."""
    output = frame.reset_index()
    output.to_csv(path, mode="a", header=not path.exists(), index=False)
    return len(output)


def _schema(connection):
    connection.executescript("""
    CREATE TABLE IF NOT EXISTS team_snapshots (
        provider TEXT NOT NULL, league_id TEXT NOT NULL, season INTEGER NOT NULL,
        matchup_period INTEGER NOT NULL, matchup_id INTEGER, timestamp INTEGER NOT NULL,
        team_id INTEGER NOT NULL, opponent_id INTEGER, score_live REAL,
        projected_live REAL, win_probability REAL
    );
    CREATE TABLE IF NOT EXISTS player_snapshots (
        provider TEXT NOT NULL, league_id TEXT NOT NULL, season INTEGER NOT NULL,
        matchup_period INTEGER NOT NULL, matchup_id INTEGER, timestamp INTEGER NOT NULL,
        team_id INTEGER NOT NULL, player_id INTEGER NOT NULL, lineup_slot_id TEXT,
        points_live REAL, projected REAL, ceiling REAL, projection_spread REAL
    );
    CREATE TABLE IF NOT EXISTS team_metadata (
        provider TEXT NOT NULL, league_id TEXT NOT NULL, season INTEGER NOT NULL,
        matchup_period INTEGER NOT NULL, team_id INTEGER NOT NULL, team_name TEXT,
        logo_url TEXT, timestamp INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS league_metadata (
        provider TEXT NOT NULL, league_id TEXT NOT NULL, season INTEGER NOT NULL,
        league_name TEXT, timestamp INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS player_metadata (
        provider TEXT NOT NULL, league_id TEXT NOT NULL, season INTEGER NOT NULL,
        matchup_period INTEGER NOT NULL, player_id INTEGER NOT NULL, timestamp INTEGER NOT NULL,
        player_name TEXT, position TEXT
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


def _sleeper_eligible(position, roster_positions):
    return list(dict.fromkeys(slot for slot in roster_positions if
        slot == "BN" or slot == position
        or (slot == "FLEX" and position in {"RB", "WR", "TE"})
        or (slot == "SUPER_FLEX" and position in {"QB", "RB", "WR", "TE"})))


def _espn_position(position_id):
    return position_id


def _player_data(data, provider, league_id, season, week, timestamp):
    snapshots = []
    metadata = {}
    if provider == "espn":
        teams = {t.get("id"): t for t in data.get("teams", [])}
        for matchup in data.get("schedule", []):
            if matchup.get("matchupPeriodId") != week:
                continue
            for side in ("away", "home"):
                team = matchup.get(side) or {}
                for entry in (team.get("rosterForCurrentScoringPeriod") or {}).get("entries", []):
                    p = (entry.get("playerPoolEntry") or {}).get("player") or {}
                    stats = p.get("stats") or []
                    current = next((s for s in stats
                        if s.get("scoringPeriodId") == week and s.get("statSourceId") == 1),
                        stats[0] if stats else {})
                    projected = current.get("appliedTotal")
                    ceiling = current.get("appliedTotalCeiling")
                    pid = p.get("id")
                    if pid is None:
                        continue
                    snapshots.append((provider, str(league_id), season, week,
                        matchup.get("id"), timestamp, team.get("teamId"), pid,
                        entry.get("lineupSlotId"), None, projected, ceiling,
                        ceiling - projected if ceiling is not None and projected is not None else None))
                    metadata[pid] = (provider, str(league_id), season, week, pid,
                        timestamp, p.get("fullName"),
                        _espn_position(p.get("defaultPositionId")))
    else:
        league = data.get("league", {})
        key = _sleeper_projection_key(league.get("scoring_settings"))
        projections = {str(p.get("player_id")): p
                       for p in data.get("player_data", {}).get("projections", [])}
        stats = {str(p.get("player_id")): p for p in
                 data.get("player_data", {}).get("stats", [])}
        roster_positions = league.get("roster_positions", [])
        for matchup in data.get("matchups", []):
            for slot, player_id in enumerate(matchup.get("starters") or []):
                pid = str(player_id)
                projection = projections.get(pid, {})
                player = projection.get("player") or {}
                projected = (projection.get("stats") or {}).get(key)
                if projected is None or not pid.isdigit():
                    continue
                position = player.get("position")
                fantasy = player.get("fantasy_positions") or ([position] if position else [])
                actual = (stats.get(pid, {}).get("stats") or {}).get(key)
                numeric_id = int(pid)
                snapshots.append((provider, str(league_id), season, week,
                    matchup.get("matchup_id"), timestamp, matchup.get("roster_id"),
                    numeric_id, slot, actual, projected, None, None))
                metadata[numeric_id] = (provider, str(league_id), season, week,
                    numeric_id, timestamp,
                    " ".join(filter(None, [player.get("first_name"), player.get("last_name")])),
                    position)
    return snapshots, list(metadata.values())


def _append_changed(connection, table, frame, key_columns):
    """Append metadata rows only when the weekly value is new or changed."""
    if frame.empty:
        return
    existing = pd.read_sql_query(f"SELECT * FROM {table}", connection)
    if existing.empty:
        frame.to_sql(table, connection, if_exists="append", index=False)
        return
    compare_columns = [column for column in frame.columns if column != "timestamp"]
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
            not (
                pd.isna(row[column]) and pd.isna(previous[column])
            )
            and row[column] != previous[column]
            for column in compare_columns
        ):
            changed.append(row)
    if changed:
        pd.DataFrame(changed, columns=frame.columns).to_sql(
            table, connection, if_exists="append", index=False
        )

def write_sqlite_snapshot(frame, *, provider, league_id, season, matchup_period,
                          data=None, path=SQLITE_PATH):
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
                    league_name = (data.get("settings") or {}).get("name") or league_name
                league_metadata = pd.DataFrame([(
                    provider, str(league_id), season, league_name, poll_timestamp
                )], columns=["provider", "league_id", "season", "league_name", "timestamp"])
                _append_changed(connection, "league_metadata", league_metadata,
                    ["provider", "league_id", "season"])
        return 0
    timestamp = output["time"].map(_unix_seconds)
    poll_timestamp = int(timestamp.iloc[0])
    team_rows = pd.DataFrame({
        "provider": provider, "league_id": str(league_id), "season": season,
        "matchup_period": matchup_period, "timestamp": timestamp,
        "matchup_id": output["Matchup"], "team_id": output["team_id"],
        "opponent_id": output["opponent_id"], "score_live": output["TotalPointsLive"],
        "projected_live": output["Projected"].round(2), "win_probability": output["WinChance"],
    })
    team_rows = team_rows[["provider", "league_id", "season", "matchup_period",
        "matchup_id", "timestamp", "team_id", "opponent_id", "score_live",
        "projected_live", "win_probability"]]
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        _schema(connection)
        team_rows.to_sql("team_snapshots", connection, if_exists="append", index=False)
        if data is None:
            return len(team_rows)
        player_rows, player_meta = _player_data(
            data, provider, league_id, season, matchup_period, poll_timestamp)
        pd.DataFrame(player_rows, columns=["provider", "league_id", "season",
            "matchup_period", "matchup_id", "timestamp", "team_id", "player_id",
            "lineup_slot_id", "points_live", "projected", "ceiling",
            "projection_spread"]).to_sql("player_snapshots", connection,
            if_exists="append", index=False)
        if provider == "espn":
            team_meta = []
            for team in data.get("teams", []):
                team_meta.append((provider, str(league_id), season, matchup_period,
                    team.get("id"), team.get("name"), team.get("logo"), poll_timestamp))
        else:
            users = {str(u.get("user_id")): u for u in data.get("users", [])}
            team_meta = []
            for roster in data.get("rosters", []):
                user = users.get(str(roster.get("owner_id")), {})
                meta = user.get("metadata") or {}
                team_meta.append((provider, str(league_id), season, matchup_period,
                    roster.get("roster_id"), meta.get("team_name") or user.get("display_name"),
                    meta.get("avatar") or user.get("avatar"), poll_timestamp))
        team_metadata = pd.DataFrame(team_meta, columns=["provider", "league_id", "season",
            "matchup_period", "team_id", "team_name", "logo_url", "timestamp"])
        _append_changed(connection, "team_metadata", team_metadata,
            ["provider", "league_id", "season", "matchup_period", "team_id"])
        league_name = (data.get("league") or {}).get("name") or data.get("name")
        if provider == "espn":
            league_name = (data.get("settings") or {}).get("name") or league_name
        league_metadata = pd.DataFrame([(
            provider, str(league_id), season, league_name, poll_timestamp
        )], columns=["provider", "league_id", "season", "league_name", "timestamp"])
        _append_changed(connection, "league_metadata", league_metadata,
            ["provider", "league_id", "season"])
        player_metadata = pd.DataFrame(player_meta, columns=["provider", "league_id", "season",
            "matchup_period", "player_id", "timestamp", "player_name", "position"])
        _append_changed(connection, "player_metadata", player_metadata,
            ["provider", "league_id", "season", "matchup_period", "player_id"])
    return len(team_rows)















def export_sqlite_csvs(source, output_dir):
    """Export SQLite tables with UTC epoch timestamps rendered in ET to seconds."""
    source = Path(source)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    tables = ("league_metadata", "team_snapshots", "player_snapshots",
              "team_metadata", "player_metadata")
    with sqlite3.connect(source) as connection:
        for table in tables:
            frame = pd.read_sql_query(f"SELECT * FROM {table}", connection)
            if "timestamp" in frame.columns and not frame.empty:
                frame["timestamp"] = (
                    pd.to_datetime(frame["timestamp"], unit="s", utc=True)
                    .dt.tz_convert("America/New_York")
                    .dt.strftime("%Y-%m-%d %H:%M:%S")
                )
            frame.to_csv(output_dir / f"{table}.csv", index=False)
