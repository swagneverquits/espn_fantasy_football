"""Convert Sleeper API responses into the common snapshot format."""

import datetime

import pandas as pd


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
        team_name = roster_names[roster_id]
        opponent_id = opponent.get("roster_id")
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
                    "Score": matchup.get("points", 0),
                    "TotalPoints": matchup.get("points", 0),
                    "TotalPointsLive": matchup.get("points", 0),
                    "WinChance": None,
                    "Projected": None,
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
