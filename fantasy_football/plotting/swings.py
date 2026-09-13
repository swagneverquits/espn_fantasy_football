"""Derived win-probability swing detection for matchup reports."""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from fantasy_football.constants import TIMESTAMP_COL

from .constants import WIN_CHANCE_COL


@dataclass(frozen=True)
class ProbabilitySwing:
    """One adjacent-poll probability change."""

    timestamp: object
    before: float
    after: float
    delta_pp: float


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
    return [
        ProbabilitySwing(
            timestamp=row[TIMESTAMP_COL],
            before=float(before),
            after=float(row[WIN_CHANCE_COL]),
            delta_pp=float(delta),
        )
        for (_, row), (_, before), (_, delta) in zip(
            rows.iterrows(), prior.items(), deltas.items()
        )
    ]


def largest_probability_swings(
    frame: pd.DataFrame, *, minimum_pp: float = 0.0
) -> list[ProbabilitySwing]:
    """Return every timestamp tied for the largest qualifying probability move."""
    swings = probability_swings(frame, minimum_pp=minimum_pp)
    if not swings:
        return []
    largest = max(abs(swing.delta_pp) for swing in swings)
    return [swing for swing in swings if np.isclose(abs(swing.delta_pp), largest)]
