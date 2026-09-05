"""Normalize ESPN payloads into the common snapshot tables."""

import logging
import time

from fantasy_football.snapshot import Snapshot

logger = logging.getLogger(__name__)


def current_week(data: dict) -> int:
    status = data.get("status", {})
    week = status.get("currentMatchupPeriod") or data.get("scoringPeriodId")
    if not week:
        raise ValueError("ESPN response did not contain a current matchup period")
    return int(week)


def parse_snapshot(
    data: dict, *, league_id: str | int, season: int, timestamp: int | None = None
) -> Snapshot:
    timestamp = int(time.time()) if timestamp is None else timestamp
    week = current_week(data)
    teams = []
    for matchup in data.get("schedule", []):
        if matchup.get("matchupPeriodId") != week:
            continue
        for side, other in (("away", "home"), ("home", "away")):
            team = matchup.get(side) or {}
            if team.get("teamId") is None:
                continue
            if team.get("winProbability") is None:
                logger.warning(
                    "Matchup %s team %s has no winProbability; skipping row",
                    matchup.get("id"),
                    team["teamId"],
                )
                continue
            score = team.get("totalPointsLive")
            if score is None:
                score = team.get("totalPoints")
            teams.append(
                {
                    "matchup_id": matchup.get("id"),
                    "team_id": team["teamId"],
                    "opponent_id": (matchup.get(other) or {}).get("teamId"),
                    "score_live": score,
                    "projected_live": team.get("totalProjectedPointsLive"),
                    "win_probability": team["winProbability"],
                }
            )
    metadata = [
        {
            "team_id": team.get("id"),
            "team_name": team.get("name"),
            "logo_url": team.get("logo"),
        }
        for team in data.get("teams", [])
    ]
    players, player_metadata = _player_data(data, league_id, season, week, timestamp)
    return Snapshot.from_records(
        provider="espn",
        league_id=league_id,
        season=season,
        matchup_period=week,
        timestamp=timestamp,
        league_name=(data.get("settings") or {}).get("name") or data.get("name"),
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
    scoring_period = (
        data.get("scoringPeriodId")
        or (data.get("status") or {}).get("currentScoringPeriod")
        or week
    )
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
                        if stat.get("scoringPeriodId") == scoring_period
                        and stat.get("statSourceId") == 1
                    ),
                    {},
                )
                actual = next(
                    (
                        stat
                        for stat in stats
                        if stat.get("scoringPeriodId") == scoring_period
                        and stat.get("statSourceId") == 0
                    ),
                    {},
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
                        actual.get("appliedTotal"),
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
                    player.get("defaultPositionId"),
                )
    return snapshots, list(metadata.values())
