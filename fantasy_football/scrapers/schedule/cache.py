"""Cross-process schedule cache with OS-managed locks and atomic publication."""

from __future__ import annotations

import errno
import json
import os
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .scraper import NFLGame, fetch_nfl_game_starts

CACHE_PATH = Path(
    os.getenv(
        "FANTASY_FOOTBALL_SCHEDULE_CACHE",
        str(Path(tempfile.gettempdir()) / "fantasy_football_schedule.json"),
    )
)
LOCK_PATH = CACHE_PATH.with_suffix(".lock")
LOCK_WAIT_SECONDS = 35
LOCK_POLL_SECONDS = 0.1


def _read_cache() -> tuple[list[NFLGame], float] | None:
    try:
        with CACHE_PATH.open(encoding="utf-8") as file:
            payload = json.load(file)
            modified = os.fstat(file.fileno()).st_mtime
        games = [
            NFLGame(datetime.fromisoformat(row["kickoff"]), row.get("nfl_week"))
            for row in payload["games"]
        ]
        return games, modified
    except (KeyError, TypeError, ValueError, AttributeError, OSError):
        return None


def read_cached_schedule() -> tuple[list[NFLGame], float] | None:
    """Read the last schedule for monitoring, without fetching or acquiring a lock."""
    return _read_cache()


def _fresh_games(refresh_seconds: int) -> list[NFLGame] | None:
    cached = _read_cache()
    if cached is not None and 0 <= time.time() - cached[1] < refresh_seconds:
        return cached[0]
    return None


def _write_cache(games: list[NFLGame]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=CACHE_PATH.parent, suffix=".tmp", delete=False
    ) as file:
        temporary = Path(file.name)
    try:
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
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def _schedule_lock() -> Iterator[bool]:
    """The OS releases ownership on close or process exit; the file stays in place."""
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("a+b") as file:
        if os.name == "nt":
            import msvcrt

            if os.fstat(file.fileno()).st_size == 0:
                file.write(b"0")
                file.flush()
            file.seek(0)
            try:
                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as error:
                if error.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                    raise
                yield False
                return
            try:
                yield True
            finally:
                file.seek(0)
                msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            try:
                fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                yield False
                return
            try:
                yield True
            finally:
                fcntl.flock(file.fileno(), fcntl.LOCK_UN)


def get_game_starts(
    now: datetime, *, refresh_seconds: int
) -> tuple[list[NFLGame], bool]:
    """Wait for a fresh shared schedule, or refresh it while holding the lock."""
    if refresh_seconds <= 0:
        raise ValueError("refresh_seconds must be positive")
    deadline = time.monotonic() + LOCK_WAIT_SECONDS
    while True:
        games = _fresh_games(refresh_seconds)
        if games is not None:
            return games, False
        with _schedule_lock() as acquired:
            if acquired:
                # Another worker may have published between our read and acquisition.
                games = _fresh_games(refresh_seconds)
                if games is not None:
                    return games, False
                games = fetch_nfl_game_starts(now)
                _write_cache(games)
                return games, True
        if time.monotonic() >= deadline:
            raise TimeoutError("Timed out waiting for a fresh NFL schedule")
        time.sleep(LOCK_POLL_SECONDS)
