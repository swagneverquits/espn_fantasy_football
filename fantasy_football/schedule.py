"""NFL game windows used to gate live fantasy polling."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fantasy_football.constants import (
    DEFAULT_GAME_WINDOW_SECONDS,
    DEFAULT_PREGAME_BUFFER_SECONDS,
)
from fantasy_football.scrapers.schedule import fetch_nfl_game_starts


@dataclass(frozen=True)
class GameWindow:
    """A polling interval around one or more overlapping NFL games."""

    start: datetime
    end: datetime


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def build_game_windows(
    game_starts: list[datetime],
    *,
    pregame_seconds: int = DEFAULT_PREGAME_BUFFER_SECONDS,
    duration_seconds: int = DEFAULT_GAME_WINDOW_SECONDS,
) -> tuple[GameWindow, ...]:
    """Build and merge polling windows around game start times."""
    windows = sorted(
        (
            GameWindow(
                _utc(start) - timedelta(seconds=pregame_seconds),
                _utc(start) + timedelta(seconds=duration_seconds),
            )
            for start in game_starts
        ),
        key=lambda window: window.start,
    )
    merged: list[GameWindow] = []
    for window in windows:
        if not merged or window.start > merged[-1].end:
            merged.append(window)
        else:
            merged[-1] = GameWindow(merged[-1].start, max(merged[-1].end, window.end))
    return tuple(merged)


def active_window(windows: tuple[GameWindow, ...], now: datetime) -> GameWindow | None:
    """Return the current window, if polling should be active."""
    now = _utc(now)
    return next(
        (window for window in windows if window.start <= now <= window.end), None
    )


def seconds_until_next_window(
    windows: tuple[GameWindow, ...], now: datetime
) -> float | None:
    """Return seconds until the next window starts, or None if there is none."""
    now = _utc(now)
    future = [window.start for window in windows if window.start > now]
    if not future:
        return None
    return max(0.0, (min(future) - now).total_seconds())
