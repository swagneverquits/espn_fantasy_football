"""NFL game windows used to gate live fantasy polling."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fantasy_football.constants import (
    DEFAULT_GAME_WINDOW_SECONDS,
    DEFAULT_PREGAME_BUFFER_SECONDS,
)

from .scraper import NFLGame


@dataclass(frozen=True)
class GameWindow:
    """A polling interval around one or more overlapping NFL games."""

    start: datetime
    end: datetime
    game_count: int = 1
    nfl_weeks: tuple[int, ...] = ()


def _utc(value: datetime) -> datetime:
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


def build_game_windows(
    games: list[datetime | NFLGame],
    *,
    pregame_seconds: int = DEFAULT_PREGAME_BUFFER_SECONDS,
    duration_seconds: int = DEFAULT_GAME_WINDOW_SECONDS,
) -> tuple[GameWindow, ...]:
    """Build and merge polling windows while retaining game metadata."""
    windows = []
    for game in games:
        kickoff = game.kickoff if isinstance(game, NFLGame) else game
        nfl_weeks = (
            ()
            if not isinstance(game, NFLGame) or game.nfl_week is None
            else (game.nfl_week,)
        )
        windows.append(
            GameWindow(
                _utc(kickoff) - timedelta(seconds=pregame_seconds),
                _utc(kickoff) + timedelta(seconds=duration_seconds),
                1,
                nfl_weeks,
            )
        )
    windows.sort(key=lambda window: window.start)
    merged: list[GameWindow] = []
    for window in windows:
        if not merged or window.start > merged[-1].end:
            merged.append(window)
        else:
            prior = merged[-1]
            merged[-1] = GameWindow(
                prior.start,
                max(prior.end, window.end),
                prior.game_count + window.game_count,
                tuple(sorted(set(prior.nfl_weeks + window.nfl_weeks))),
            )
    return tuple(merged)


def active_window(windows: tuple[GameWindow, ...], now: datetime) -> GameWindow | None:
    now = _utc(now)
    return next(
        (window for window in windows if window.start <= now <= window.end), None
    )


def seconds_until_next_window(
    windows: tuple[GameWindow, ...], now: datetime
) -> float | None:
    now = _utc(now)
    future = [window.start for window in windows if window.start > now]
    if not future:
        return None
    return max(0.0, (min(future) - now).total_seconds())
