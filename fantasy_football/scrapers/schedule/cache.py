"""Shared cross-process cache for the NFL schedule."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path

from .scraper import NFLGame, fetch_nfl_game_starts

CACHE_PATH = Path(
    os.getenv("FANTASY_FOOTBALL_SCHEDULE_CACHE", "/tmp/fantasy_football_schedule.json")
)
LOCK_PATH = CACHE_PATH.with_suffix(".lock")


def _read_cache() -> tuple[list[NFLGame], float] | None:
    try:
        payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        games = [
            NFLGame(datetime.fromisoformat(row["kickoff"]), row.get("nfl_week"))
            for row in payload["games"]
        ]
        return games, CACHE_PATH.stat().st_mtime
    except (FileNotFoundError, KeyError, TypeError, ValueError, OSError):
        return None


def _write_cache(games: list[NFLGame]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = CACHE_PATH.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {
                "games": [
                    {"kickoff": game.kickoff.isoformat(), "nfl_week": game.nfl_week}
                    for game in games
                ]
            }
        ),
        encoding="utf-8",
    )
    temporary.replace(CACHE_PATH)


def get_game_starts(
    now: datetime, *, refresh_seconds: int
) -> tuple[list[NFLGame], bool]:
    """Return cached games and whether this process refreshed the cache."""
    cached = _read_cache()
    if cached and time.time() - cached[1] < refresh_seconds:
        return cached[0], False
    acquired = False
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        acquired = True
        cached = _read_cache()
        if cached and time.time() - cached[1] < refresh_seconds:
            return cached[0], False
        games = fetch_nfl_game_starts(now)
        _write_cache(games)
        return games, True
    except FileExistsError:
        for _ in range(100):
            time.sleep(0.1)
            cached = _read_cache()
            if cached:
                return cached[0], False
        return fetch_nfl_game_starts(now), False
    finally:
        if acquired:
            try:
                LOCK_PATH.unlink()
            except FileNotFoundError:
                pass
