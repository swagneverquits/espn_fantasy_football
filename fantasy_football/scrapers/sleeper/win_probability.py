"""Sleeper's frontend matchup win-probability calculation."""

import logging
import math

logger = logging.getLogger(__name__)


def nfl_remaining_seconds(metadata: dict | None) -> int:
    """Return Sleeper's NFL game-clock value in seconds remaining."""
    metadata = metadata or {}
    quarter = metadata.get("quarter")
    if not quarter:
        return 3600
    if metadata.get("is_over") or quarter in {"OT", "F", "F/OT"}:
        return 0
    if quarter in {"HALF", "Halftime"}:
        return 1800
    try:
        quarter_number = int(quarter)
    except (TypeError, ValueError):
        return 3600
    clock = str(metadata.get("time_remaining") or "00:00").split(":")
    minutes = int(clock[0]) if len(clock) > 0 and clock[0].isdigit() else 0
    seconds = int(clock[1]) if len(clock) > 1 and clock[1].isdigit() else 0
    completed_quarters = 4 - min(quarter_number, 4)
    return 15 * completed_quarters * 60 + minutes * 60 + seconds


def sleeper_dynamic_projection(
    actual: object,
    projected: object,
    remaining_seconds: int,
    *,
    is_team_defense: bool = False,
) -> float:
    """Reproduce Sleeper's browser-side live player projection formula."""
    actual_value = _finite_or_zero(actual)
    projected_value = _finite_or_zero(projected)
    fraction_remaining = remaining_seconds / 3600
    elapsed_minutes = 60 - remaining_seconds / 60
    pace_denominator = elapsed_minutes or 1
    pace_projection = (
        actual_value
        + actual_value / pace_denominator * remaining_seconds / 60 * fraction_remaining
    )

    if is_team_defense:
        lower = 0.05 * fraction_remaining * pace_projection
        central = (0.1 + 0.15 * (1 - fraction_remaining)) * pace_projection
        upper = 0.15 * fraction_remaining * pace_projection
    else:
        lower = 0.2 * fraction_remaining * pace_projection
        central = (0.35 + 0.65 * (1 - fraction_remaining)) * pace_projection
        upper = 0.45 * fraction_remaining * pace_projection

    maximum_projection = max(lower + central + upper, actual_value)
    baseline = (
        projected_value
        if fraction_remaining >= 1
        else max(projected_value, actual_value)
    )
    if fraction_remaining <= 0 and actual_value < 0:
        return actual_value
    return baseline + (1 - fraction_remaining) * (maximum_projection - baseline)


def _finite_or_zero(value: object) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return value if math.isfinite(value) else 0.0


def _score_distribution(actual: float, projected: float) -> tuple[float, float]:
    """Return Sleeper's normal-distribution mean and variance for a team."""
    actual = float(actual)
    projected = float(projected)
    if not math.isfinite(actual) or not math.isfinite(projected):
        raise ValueError("Scores and projections must be finite")
    if projected == 0:
        return projected, 0.1

    scale = 1 + 10 * (1 - actual / projected)
    if scale <= 0:
        raise ValueError("Projection is outside the probability formula's domain")
    standard_deviation = math.sqrt((actual - projected) ** 2 / scale)
    variance = standard_deviation**2 or 0.1
    return projected, variance


def sleeper_win_probability(
    actual_team_1: float,
    projected_team_1: float,
    actual_team_2: float,
    projected_team_2: float,
) -> tuple[float, float] | None:
    """Return Sleeper's unrounded team probabilities as values from 0 to 1.

    This mirrors the probability utility in Sleeper's web bundle, including
    its 1%-99% bounds and its exact-score handling. Invalid inputs produce
    no probability, allowing actual scores to be saved without an invented estimate.
    """
    try:
        mean_1, variance_1 = _score_distribution(actual_team_1, projected_team_1)
        mean_2, variance_2 = _score_distribution(actual_team_2, projected_team_2)
    except (ValueError, OverflowError) as error:
        logger.warning(
            "Sleeper probability unavailable: %s; scores=%s",
            error,
            (actual_team_1, projected_team_1, actual_team_2, projected_team_2),
        )
        return None

    if round(actual_team_1, 2) == round(projected_team_1, 2) and round(
        actual_team_2, 2
    ) == round(projected_team_2, 2):
        if actual_team_1 == actual_team_2:
            return 0.0, 0.0
        if actual_team_1 < actual_team_2:
            return 0.0, 1.0
        return 1.0, 0.0

    mean_difference = mean_1 - mean_2
    variance_difference = variance_1 + variance_2
    cdf_at_zero = 0.5 * (
        1 + math.erf((0 - mean_difference) / math.sqrt(2 * variance_difference))
    )
    probability_1 = max(0.01, min(0.99, 1 - cdf_at_zero))
    return probability_1, max(0.01, min(0.99, 1 - probability_1))


def sleeper_win_percentage(*scores: float) -> tuple[int, int] | None:
    """Return the integer percentages displayed by Sleeper."""
    probabilities = sleeper_win_probability(*scores)
    if probabilities is None:
        return None
    probability_1, probability_2 = probabilities
    return round(100 * probability_1), round(100 * probability_2)
