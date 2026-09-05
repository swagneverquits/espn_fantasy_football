"""Normalize Sleeper payloads into the common snapshot tables."""

import time

from fantasy_football.constants import MATCHUP_ID_COL
from fantasy_football.snapshot import Snapshot

from .win_probability import sleeper_win_percentage


def _projection_key(scoring_settings):
    settings = scoring_settings or {}
    if settings.get("rec") == 1 and settings.get("rec_yd") == 0.1:
        return "pts_ppr"
    if settings.get("rec") == 0.5 and settings.get("rec_yd") == 0.1:
        return "pts_half_ppr"
    return "pts_std"


def _projected_totals(data):
    league = data.get("league", {})
    key = _projection_key(league.get("scoring_settings"))
    projections = data.get("player_data", {}).get("projections", [])
    projection_map = {
        str(item.get("player_id")): (item.get("stats") or {}).get(key)
        for item in projections
        if item.get("player_id") is not None
    }
    totals = {}
    for matchup in data.get("matchups", []):
        values = [
            projection_map.get(str(player_id))
            for player_id in matchup.get("starters", [])
        ]
        values = [float(value) for value in values if value is not None]
        totals[matchup["roster_id"]] = sum(values) if values else None
    return totals


def parse_snapshot(
    data: dict, *, league_id: str | int, season: int, timestamp: int | None = None
) -> Snapshot:
    timestamp = int(time.time()) if timestamp is None else timestamp
    week = int(data["week"])
    users = {str(user["user_id"]): user for user in data.get("users", [])}
    metadata = []
    for roster in data.get("rosters", []):
        user = users.get(str(roster.get("owner_id")), {})
        details = user.get("metadata") or {}
        metadata.append(
            {
                "team_id": roster["roster_id"],
                "team_name": details.get("team_name")
                or user.get("display_name")
                or str(roster["roster_id"]),
                "logo_url": details.get("avatar") or user.get("avatar"),
            }
        )
    projected = _projected_totals(data)
    matchups = [
        row for row in data.get("matchups", []) if row.get("matchup_id") is not None
    ]
    teams = []
    for matchup in matchups:
        team_id = matchup["roster_id"]
        opponent = next(
            (
                row
                for row in matchups
                if row["matchup_id"] == matchup["matchup_id"]
                and row["roster_id"] != team_id
            ),
            {},
        )
        actual = matchup.get("points") or 0
        own_projection = projected.get(team_id)
        opponent_projection = projected.get(opponent.get("roster_id"))
        percentages = None
        if own_projection is not None and opponent_projection is not None:
            percentages = sleeper_win_percentage(
                actual, own_projection, opponent.get("points") or 0, opponent_projection
            )
        teams.append(
            {
                "matchup_id": matchup["matchup_id"],
                "team_id": team_id,
                "opponent_id": opponent.get("roster_id"),
                "score_live": actual,
                "projected_live": own_projection,
                "win_probability": (
                    percentages[0] / 100 if percentages is not None else None
                ),
            }
        )
    players, player_metadata = _player_data(data, league_id, season, week, timestamp)
    return Snapshot.from_records(
        provider="sleeper",
        league_id=league_id,
        season=season,
        matchup_period=week,
        timestamp=timestamp,
        league_name=(data.get("league") or {}).get("name"),
        team_snapshots=teams,
        team_metadata=metadata,
        player_snapshots=players,
        player_metadata=player_metadata,
    )


def _player_data(
    data: dict, league_id: str | int, season: int, week: int, timestamp: int
) -> tuple[list[tuple], list[tuple]]:
    snapshots = []
    metadata = {}
    scoring_key = _projection_key((data.get("league") or {}).get("scoring_settings"))
    projections = {
        str(player.get("player_id")): player
        for player in (data.get("player_data") or {}).get("projections", [])
    }
    stats = {
        str(player.get("player_id")): player
        for player in (data.get("player_data") or {}).get("stats", [])
    }
    for matchup in data.get("matchups", []):
        for slot, player_id in enumerate(matchup.get("starters") or []):
            if player_id is None or str(player_id) in {"", "0"}:
                continue
            player_key = str(player_id)
            projection = projections.get(player_key, {})
            projected = (projection.get("stats") or {}).get(scoring_key)
            stat = stats.get(player_key, {})
            player = projection.get("player") or stat.get("player") or {}
            # Matchup points include league-specific scoring; stats are a fallback.
            actual = (matchup.get("players_points") or {}).get(player_key)
            if actual is None:
                actual = (stat.get("stats") or {}).get(scoring_key)
            snapshots.append(
                (
                    "sleeper",
                    str(league_id),
                    season,
                    week,
                    matchup.get(MATCHUP_ID_COL),
                    timestamp,
                    matchup.get("roster_id"),
                    player_key,
                    slot,
                    actual,
                    projected,
                    None,
                    None,
                )
            )
            metadata[player_key] = (
                "sleeper",
                str(league_id),
                season,
                week,
                player_key,
                timestamp,
                " ".join(
                    filter(None, [player.get("first_name"), player.get("last_name")])
                )
                or None,
                player.get("position"),
            )
    return snapshots, list(metadata.values())
