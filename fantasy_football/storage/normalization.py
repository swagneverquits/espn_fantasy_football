"""Provider-specific normalization helpers for snapshot persistence."""

from __future__ import annotations

import pandas as pd

from fantasy_football.constants import MATCHUP_ID_COL


def unix_seconds(value: object) -> int:
    """Convert a timestamp to UTC Unix seconds."""
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    return int(timestamp.timestamp())


def _sleeper_projection_key(settings: dict | None) -> str:
    scoring = (settings or {}).get("rec")
    if scoring == 1:
        return "pts_ppr"
    if scoring == 0.5:
        return "pts_half_ppr"
    return "pts_std"


def _espn_player_data(
    data: dict, league_id: str | int, season: int, week: int, timestamp: int
):
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


def _sleeper_player_data(
    data: dict, league_id: str | int, season: int, week: int, timestamp: int
):
    snapshots = []
    metadata = {}
    scoring_key = _sleeper_projection_key(
        (data.get("league") or {}).get("scoring_settings")
    )
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


def player_data(
    data: dict,
    provider: str,
    league_id: str | int,
    season: int,
    week: int,
    timestamp: int,
):
    """Return normalized player snapshot rows and metadata rows."""
    if provider == "espn":
        return _espn_player_data(data, league_id, season, week, timestamp)
    return _sleeper_player_data(data, league_id, season, week, timestamp)
