"""Sleeper's frontend matchup win-probability calculation."""

import math


def _score_distribution(actual: float, projected: float) -> tuple[float, float]:
    """Return Sleeper's normal-distribution mean and variance for a team."""
    actual = float(actual)
    projected = float(projected)
    if projected == 0:
        return projected, 0.1

    scale = 1 + 10 * (1 - actual / projected)
    standard_deviation = math.sqrt((actual - projected) ** 2 / scale)
    variance = standard_deviation**2 or 0.1
    return projected, variance


def sleeper_win_probability(
    actual_team_1: float,
    projected_team_1: float,
    actual_team_2: float,
    projected_team_2: float,
) -> tuple[float, float]:
    """Return Sleeper's unrounded team probabilities as values from 0 to 1.

    This mirrors the probability utility in Sleeper's web bundle, including
    its 1%-99% bounds and its exact-score handling.
    """
    if round(actual_team_1, 2) == round(projected_team_1, 2) and round(
        actual_team_2, 2
    ) == round(projected_team_2, 2):
        if actual_team_1 == actual_team_2:
            return 0.0, 0.0
        if actual_team_1 < actual_team_2:
            return 0.0, 1.0
        return 1.0, 0.0

    mean_1, variance_1 = _score_distribution(actual_team_1, projected_team_1)
    mean_2, variance_2 = _score_distribution(actual_team_2, projected_team_2)
    mean_difference = mean_1 - mean_2
    variance_difference = variance_1 + variance_2
    cdf_at_zero = 0.5 * (
        1 + math.erf((0 - mean_difference) / math.sqrt(2 * variance_difference))
    )
    probability_1 = max(0.01, min(0.99, 1 - cdf_at_zero))
    return probability_1, max(0.01, min(0.99, 1 - probability_1))


def sleeper_win_percentage(*scores: float) -> tuple[int, int]:
    """Return the integer percentages displayed by Sleeper."""
    probability_1, probability_2 = sleeper_win_probability(*scores)
    return round(100 * probability_1), round(100 * probability_2)
