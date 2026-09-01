"""Convert Sleeper API responses into the common snapshot format."""

import datetime

import pandas as pd

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


def matchup_rows(data: dict, timestamp=None, matchup_period=None) -> pd.DataFrame:
    """Return one row per Sleeper roster in the selected matchup period."""
    timestamp = timestamp or datetime.datetime.now().astimezone()
    users = {str(user["user_id"]): user for user in data["users"]}
    roster_names = {}
    for roster in data["rosters"]:
        user = users.get(str(roster.get("owner_id")), {})
        metadata = user.get("metadata") or {}
        roster_names[roster["roster_id"]] = (
            metadata.get("team_name")
            or user.get("display_name")
            or str(roster["roster_id"])
        )

    projected_totals = _projected_totals(data)
    rows = []
    matchups = [m for m in data["matchups"] if m.get("matchup_id") is not None]
    for matchup in matchups:
        roster_id = matchup["roster_id"]
        opponent = next(
            (
                m
                for m in matchups
                if m.get("matchup_id") == matchup.get("matchup_id")
                and m["roster_id"] != roster_id
            ),
            {},
        )
        opponent_id = opponent.get("roster_id")
        actual = matchup.get("points") or 0
        opponent_actual = opponent.get("points") or 0
        projected = projected_totals.get(roster_id)
        opponent_projected = projected_totals.get(opponent_id)
        win_chance = None
        if projected is not None and opponent_projected is not None:
            win_chance = (
                sleeper_win_percentage(
                    actual,
                    projected,
                    opponent_actual,
                    opponent_projected,
                )[0]
                / 100
            )

        team_name = roster_names[roster_id]
        rows.append(
            (
                (timestamp, team_name),
                {
                    "Matchup": matchup.get("matchup_id"),
                    "MatchupPeriod": matchup_period or data["week"],
                    "Winner": None,
                    "team_id": roster_id,
                    "team_name": team_name,
                    "opponent_id": opponent_id,
                    "opponent_name": roster_names.get(opponent_id),
                    "home_or_away": None,
                    "Score": actual,
                    "TotalPoints": actual,
                    "TotalPointsLive": actual,
                    "WinChance": win_chance,
                    "Projected": projected,
                },
            )
        )

    columns = [
        "Matchup",
        "MatchupPeriod",
        "Winner",
        "team_id",
        "team_name",
        "opponent_id",
        "opponent_name",
        "home_or_away",
        "Score",
        "TotalPoints",
        "TotalPointsLive",
        "WinChance",
        "Projected",
    ]
    if not rows:
        return pd.DataFrame(columns=columns)
    frame = pd.DataFrame(dict(rows)).T
    frame.index.names = ["time", "team"]
    return frame
