"""Activity windows and shared compressed time coordinates."""

import matplotlib.dates as mdates
import numpy as np
import pandas as pd

from fantasy_football.constants import TIMESTAMP_COL


def game_windows(
    data: pd.DataFrame, gap_seconds: int
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Infer independent collection windows from gaps in the timestamps."""
    if gap_seconds <= 0:
        raise ValueError("window_gap_seconds must be positive")
    times = data[TIMESTAMP_COL].drop_duplicates().sort_values()
    groups = times.diff().dt.total_seconds().gt(gap_seconds).cumsum()
    grouped = list(times.groupby(groups))
    if len(grouped) > 1 and len(grouped[-1][1]) == 1 and len(grouped[-2][1]) > 1:
        grouped.pop()
    return [(group.iloc[0], group.iloc[-1]) for _, group in grouped]


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
