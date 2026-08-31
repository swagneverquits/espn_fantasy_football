"""Convert ESPN league API responses into enriched snapshot rows."""

import datetime
import json
import logging

import pandas as pd


def current_week(data: dict) -> int:
    status = data.get("status", {})
    week = status.get("currentMatchupPeriod") or data.get("scoringPeriodId")
    if not week:
        raise ValueError("ESPN response did not contain a current matchup period")
    return int(week)


def _serialized(value) -> str:
    return json.dumps(value, separators=(",", ":"), default=str)


def matchup_rows(data: dict, timestamp=None, matchup_period=None) -> pd.DataFrame:
    """Return one enriched row for each team in the selected matchup period."""
    timestamp = timestamp or datetime.datetime.now().astimezone()
    team_records = {team["id"]: team for team in data.get("teams", [])}
    team_names = {
        team_id: team.get("name", str(team_id))
        for team_id, team in team_records.items()
    }
    rows = []

    for matchup in data.get("schedule", []):
        if (
            matchup_period is not None
            and matchup.get("matchupPeriodId") != matchup_period
        ):
            continue
        for side, other_side in (("away", "home"), ("home", "away")):
            team_data = matchup.get(side) or {}
            team_id = team_data.get("teamId")
            if team_id is None:
                continue
            probability = team_data.get("winProbability")
            if probability is None:
                logging.warning(
                    "Matchup %s team %s has no winProbability; skipping row",
                    matchup.get("id"),
                    team_id,
                )
                continue

            opponent_id = (matchup.get(other_side) or {}).get("teamId")
            team_record = team_records.get(team_id, {})
            roster = team_data.get("rosterForCurrentScoringPeriod") or {}
            rows.append(
                (
                    (timestamp, team_names.get(team_id, str(team_id))),
                    {
                        "Matchup": matchup.get("id"),
                        "MatchupPeriod": matchup.get("matchupPeriodId"),
                        "Winner": matchup.get("winner"),
                        "team_id": team_id,
                        "team_name": team_names.get(team_id, str(team_id)),
                        "opponent_id": opponent_id,
                        "opponent_name": team_names.get(opponent_id, str(opponent_id)),
                        "home_or_away": side,
                        "Score": team_data.get(
                            "totalPointsLive", team_data.get("totalPoints")
                        ),
                        "TotalPoints": team_data.get("totalPoints"),
                        "TotalPointsLive": team_data.get("totalPointsLive"),
                        "WinChance": probability,
                        "Projected": team_data.get("totalProjectedPointsLive"),
                        "TotalProjectedPoints": team_data.get("totalProjectedPoints"),
                        "TotalProjectedPointsLive": team_data.get(
                            "totalProjectedPointsLive"
                        ),
                        "GamesPlayed": team_data.get("gamesPlayed"),
                        "CumulativeScore": _serialized(
                            team_data.get("cumulativeScore")
                        ),
                        "CumulativeScoreLive": _serialized(
                            team_data.get("cumulativeScoreLive")
                        ),
                        "PointsByScoringPeriod": _serialized(
                            team_data.get("pointsByScoringPeriod")
                        ),
                        "RosterAppliedStatTotal": roster.get("appliedStatTotal"),
                        "RosterEntryCount": len(roster.get("entries", [])),
                        "Roster": _serialized(roster),
                        "Team": _serialized(team_record),
                        "MatchupPayload": _serialized(matchup),
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
        "TotalProjectedPoints",
        "TotalProjectedPointsLive",
        "GamesPlayed",
        "CumulativeScore",
        "CumulativeScoreLive",
        "PointsByScoringPeriod",
        "RosterAppliedStatTotal",
        "RosterEntryCount",
        "Roster",
        "Team",
        "MatchupPayload",
    ]
    if not rows:
        return pd.DataFrame(columns=columns)
    frame = pd.DataFrame(dict(rows)).T
    frame.index.names = ["time", "team"]
    return frame
