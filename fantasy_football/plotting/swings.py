"""Derived win-probability swing detection for matchup reports."""

from dataclasses import dataclass
import json
import math
from collections.abc import Iterable

import numpy as np
import pandas as pd

from fantasy_football.constants import TIMESTAMP_COL

from .constants import WIN_CHANCE_COL


@dataclass(frozen=True)
class ProbabilitySwing:
    """One adjacent-poll probability change."""

    before_timestamp: object
    timestamp: object
    before: float
    after: float
    delta_pp: float


@dataclass(frozen=True)
class NarrativeSwing:
    """A clustered probability event with a conservative football callout."""

    timestamp: object
    before: float
    after: float
    delta_pp: float
    label: str


def _timestamp_key(value: object) -> int:
    """Normalize pandas/Python timestamps to the snapshot Unix-second key."""
    if isinstance(value, pd.Timestamp):
        return int(value.timestamp())
    return int(value)


def _cluster_swings(
    swings: Iterable[ProbabilitySwing], *, max_seconds: int = 120
) -> list[ProbabilitySwing]:
    """Combine adjacent qualifying updates that belong to one short event."""
    ordered = sorted(swings, key=lambda swing: pd.Timestamp(swing.timestamp))
    if not ordered:
        return []
    clustered: list[ProbabilitySwing] = []
    current = ordered[0]
    for swing in ordered[1:]:
        elapsed = (
            pd.Timestamp(swing.timestamp) - pd.Timestamp(current.timestamp)
        ).total_seconds()
        if elapsed <= max_seconds:
            current = ProbabilitySwing(
                before_timestamp=current.before_timestamp,
                timestamp=swing.timestamp,
                before=current.before,
                after=swing.after,
                delta_pp=swing.after - current.before,
            )
        else:
            clustered.append(current)
            current = swing
    clustered.append(current)
    return clustered


def _parse_applied_points(value: object) -> tuple[float | None, dict[str, float]]:
    """Read the compact applied-points payload without assuming a provider."""
    if not isinstance(value, str) or not value:
        return None, {}
    try:
        payload = json.loads(value)
    except (TypeError, ValueError):
        return None, {}
    total = payload.get("total")
    try:
        total = float(total) if total is not None else None
    except (TypeError, ValueError):
        total = None
    components = {}
    for key, component in (payload.get("components") or {}).items():
        try:
            number = float(component)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            components[str(key)] = number
    return total, components


def _player_name(value: object) -> str:
    """Compact a player name for a phone-sized annotation."""
    name = str(value or "Unknown player").strip()
    parts = name.split()
    return f"{parts[0][0]}. {' '.join(parts[1:])}" if len(parts) > 1 else name


def _known_play_description(
    before_components: dict[str, float], after_components: dict[str, float]
) -> str | None:
    """Describe only scoring keys whose meaning is explicit in the payload."""
    changes = {
        key: after_components.get(key, 0.0) - before_components.get(key, 0.0)
        for key in set(before_components) | set(after_components)
    }
    positive = {key: value for key, value in changes.items() if value > 0}
    descriptions = (
        ("43", "receiving TD"),
        ("53", "reception"),
        ("42", "receiving yardage"),
        ("rec_td", "receiving TD"),
        ("rec_yd", "receiving yardage"),
        ("rush_td", "rushing TD"),
        ("pass_td", "passing TD"),
        ("def_td", "defensive TD"),
        ("fum_td", "fumble-return TD"),
    )
    touchdown_descriptions = {
        description
        for key, description in descriptions
        if key in positive and "TD" in description
    }
    if touchdown_descriptions:
        return next(iter(touchdown_descriptions))
    found = [description for key, description in descriptions if key in positive]
    if found:
        return " + ".join(found[:2])
    return None


def _player_event(
    players: pd.DataFrame,
    *,
    before_time: object,
    after_time: object,
    favored_team: object,
) -> tuple[str, float, str | None] | None:
    """Find the largest positive player-point change for the favored team."""
    if players.empty:
        return None
    relevant = players[players["team_id"].eq(favored_team)].copy()
    if relevant.empty:
        return None
    relevant = relevant.sort_values(TIMESTAMP_COL)
    changes = []
    for player_id, group in relevant.groupby("player_id", dropna=False):
        before = group[group[TIMESTAMP_COL] <= before_time].tail(1)
        after = group[group[TIMESTAMP_COL] <= after_time].tail(1)
        if before.empty or after.empty:
            continue
        before_total, before_components = _parse_applied_points(
            before.iloc[0].get("applied_points_json")
        )
        after_total, after_components = _parse_applied_points(
            after.iloc[0].get("applied_points_json")
        )
        if before_total is None or after_total is None:
            before_total = before.iloc[0].get("points_live")
            after_total = after.iloc[0].get("points_live")
        try:
            delta = float(after_total) - float(before_total)
        except (TypeError, ValueError):
            continue
        if delta <= 0:
            continue
        changes.append(
            (
                delta,
                _player_name(after.iloc[0].get("player_name")),
                _known_play_description(before_components, after_components),
            )
        )
    return max(changes, default=None)


def narrative_swing_annotations(
    team_frame: pd.DataFrame,
    player_frame: pd.DataFrame | None = None,
    *,
    minimum_pp: float = 50.0,
    limit: int = 2,
) -> dict[int, str]:
    """Build compact, conservative narrative labels for major WP events."""
    candidates = _cluster_swings(
        probability_swings(team_frame, minimum_pp=minimum_pp)
    )
    candidates = sorted(candidates, key=lambda swing: abs(swing.delta_pp), reverse=True)
    annotations: dict[int, str] = {}
    for swing in candidates[:limit]:
        favored_team = team_frame.iloc[0].get("team_id")
        if swing.delta_pp < 0:
            team_ids = team_frame["team_id"].drop_duplicates().tolist()
            if player_frame is not None and "team_id" in player_frame:
                team_ids = list(dict.fromkeys(team_ids + player_frame["team_id"].tolist()))
            favored_team = team_ids[1] if len(team_ids) > 1 else favored_team
        player_event = _player_event(
            player_frame if player_frame is not None else pd.DataFrame(),
            before_time=swing.before_timestamp,
            after_time=swing.timestamp,
            favored_team=favored_team,
        )
        if player_event is None:
            label = f"{swing.delta_pp:+.0f} pp"
        else:
            points, player_name, description = player_event
            first_line = (
                f"{player_name}: {description}" if description else player_name
            )
            delta_text = (
                f"+{swing.delta_pp:.0f}"
                if swing.delta_pp >= 0
                else f"\u2212{abs(swing.delta_pp):.0f}"
            )
            label = f"{first_line}\n{points:+.1f} pts \u00b7 {delta_text} pp"
        annotations[_timestamp_key(swing.timestamp)] = label
    return annotations


def probability_swings(
    frame: pd.DataFrame, *, minimum_pp: float
) -> list[ProbabilitySwing]:
    """Return every adjacent-poll move at or above a percentage threshold.

    ESPN commonly exposes whole-number percentages, so a matchup can have
    several equally large swings. Returning every qualifying event avoids
    pretending that a single event is uniquely the largest one.
    """
    columns = [TIMESTAMP_COL, WIN_CHANCE_COL]
    observations = frame[columns].copy()
    observations[WIN_CHANCE_COL] = pd.to_numeric(
        observations[WIN_CHANCE_COL], errors="coerce"
    )
    observations = observations.dropna().sort_values(TIMESTAMP_COL)
    observations = observations.drop_duplicates(TIMESTAMP_COL, keep="last")
    if len(observations) < 2:
        return []

    probabilities = observations[WIN_CHANCE_COL]
    changes = probabilities.diff() * 100
    absolute_changes = changes.abs()
    if pd.isna(absolute_changes.max()):
        return []

    qualifying = absolute_changes.ge(minimum_pp).fillna(False)
    rows = observations.loc[qualifying]
    prior = probabilities.shift(1).loc[qualifying]
    deltas = changes.loc[qualifying]
    swings = []
    for index, row in rows.iterrows():
        position = observations.index.get_loc(index)
        swings.append(
            ProbabilitySwing(
                before_timestamp=observations.iloc[position - 1][TIMESTAMP_COL],
                timestamp=row[TIMESTAMP_COL],
                before=float(prior.loc[index]),
                after=float(row[WIN_CHANCE_COL]),
                delta_pp=float(deltas.loc[index]),
            )
        )
    return swings


def largest_probability_swings(
    frame: pd.DataFrame, *, minimum_pp: float = 0.0
) -> list[ProbabilitySwing]:
    """Return every timestamp tied for the largest qualifying probability move."""
    swings = probability_swings(frame, minimum_pp=minimum_pp)
    if not swings:
        return []
    largest = max(abs(swing.delta_pp) for swing in swings)
    return [swing for swing in swings if np.isclose(abs(swing.delta_pp), largest)]
