"""Activity windows and shared compressed time coordinates."""

import logging

import matplotlib.dates as mdates
import numpy as np
import pandas as pd

from fantasy_football.constants import TIMESTAMP_COL

logger = logging.getLogger(__name__)


def _changed_within_segment(
    frame: pd.DataFrame, column: str
) -> bool:
    """Return whether any team's value changes during a timestamp segment."""
    if column not in frame:
        return False
    values = frame.dropna(subset=[column])
    if values.empty:
        return False
    if "team_id" not in values:
        return values[column].nunique() > 1
    by_team = values.groupby(["team_id", column], dropna=False).size()
    return by_team.reset_index().groupby("team_id")[column].nunique().gt(1).any()


def _segment_scores(frame: pd.DataFrame) -> tuple[object, object]:
    """Return compact first/last score summaries for diagnostic logging."""
    if "score_live" not in frame:
        return None, None
    ordered = frame.sort_values(TIMESTAMP_COL)
    if "team_id" not in ordered:
        return ordered["score_live"].iloc[0], ordered["score_live"].iloc[-1]
    first = ordered.groupby("team_id", sort=True)["score_live"].first().to_dict()
    last = ordered.groupby("team_id", sort=True)["score_live"].last().to_dict()
    return first, last


def game_windows(
    data: pd.DataFrame, gap_seconds: int
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Infer independent collection windows from gaps in the timestamps."""
    if gap_seconds <= 0:
        raise ValueError("window_gap_seconds must be positive")
    times = data[TIMESTAMP_COL].drop_duplicates().sort_values()
    groups = times.diff().dt.total_seconds().gt(gap_seconds).cumsum()
    grouped = list(times.groupby(groups))
    windows = []
    for index, (_, segment_times) in enumerate(grouped, start=1):
        segment = data[data[TIMESTAMP_COL].isin(segment_times)]
        points_changed = _changed_within_segment(segment, "score_live")
        probability_changed = _changed_within_segment(segment, "win_probability")
        # A sustained polling segment is a genuine shared collection window
        # even when this particular matchup has no scoring movement. Singleton
        # pulls are the phantom-window case we need to exclude.
        keep = len(segment_times) > 1
        first_scores, last_scores = _segment_scores(segment)
        logger.debug(
            "activity window candidate=%d start=%s end=%s duration=%s observations=%d "
            "points_changed=%s probability_changed=%s first_scores=%s last_scores=%s keep=%s",
            index,
            segment_times.iloc[0],
            segment_times.iloc[-1],
            segment_times.iloc[-1] - segment_times.iloc[0],
            len(segment_times),
            points_changed,
            probability_changed,
            first_scores,
            last_scores,
            keep,
        )
        if keep:
            windows.append((segment_times.iloc[0], segment_times.iloc[-1]))
    return windows


def compressed_timeline(windows):
    """Map active windows to a compact shared vertical coordinate."""
    raw = [(mdates.date2num(start), mdates.date2num(end)) for start, end in windows]
    durations = [end - start for start, end in raw]
    current_gap = max(max(durations, default=1 / 24) * 0.12, 0.15 / 24)
    gap = current_gap * 0.25
    segments = []
    cursor = 0.0
    for (start, end), duration in zip(raw, durations):
        segments.append((start, end, cursor, cursor + duration))
        cursor += duration + gap

    def transform(values):
        values = np.asarray(values, dtype=float)
        result = np.empty_like(values)
        for raw_start, raw_end, mapped_start, _ in segments:
            selected = (values >= raw_start) & (values <= raw_end)
            result[selected] = mapped_start + values[selected] - raw_start
        return result

    return segments, transform, cursor - gap
