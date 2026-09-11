"""Best-effort worker heartbeats and an independently attachable dashboard."""

from __future__ import annotations

import json
import logging
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rich.console import Group
    from rich.table import Table

from threading import Event, Lock, Thread
from zoneinfo import ZoneInfo

from fantasy_football.config import LeagueConfig
from fantasy_football.constants import (
    STATUS_DIR,
    STATUS_HEARTBEAT_SECONDS,
    STATUS_STALE_SECONDS,
)

logger = logging.getLogger(__name__)


class WorkerStatus:
    """One atomic status file per league; monitoring cannot stop collection."""

    def __init__(self, provider: str, league_id: str, root: Path = STATUS_DIR):
        self.path = root / f"{provider}_{league_id}.json"
        self.lock = Lock()
        self.stop = Event()
        self.started = time.monotonic()
        self.state = {
            "status": "Starting",
            "last_result": "--",
            "last_scrape": None,
            "last_success": None,
            "errors": 0,
            "uptime": 0,
        }
        self.thread = Thread(target=self._heartbeat, daemon=True)

    def __enter__(self) -> WorkerStatus:
        self.started = time.monotonic()
        self.update(status="Starting")
        self.thread.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.stop.set()
        self.thread.join()
        self.update(status="Stopped")

    def update(self, **changes: object) -> None:
        with self.lock:
            self.state.update(changes)
            self.state.update(
                heartbeat=time.time(), uptime=time.monotonic() - self.started
            )
            temporary = None
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=self.path.parent,
                    suffix=".tmp",
                    delete=False,
                ) as file:
                    temporary = Path(file.name)
                    json.dump(self.state, file)
                temporary.replace(self.path)
            except OSError:
                logger.warning(
                    "Could not write worker status: %s", self.path, exc_info=True
                )
            finally:
                if temporary is not None:
                    try:
                        temporary.unlink(missing_ok=True)
                    except OSError:
                        pass

    def _heartbeat(self) -> None:
        while not self.stop.wait(STATUS_HEARTBEAT_SECONDS):
            self.update()


def read_status(path: Path) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        for field in ("heartbeat", "uptime", "last_scrape", "last_success"):
            if data.get(field) is not None and not isinstance(
                data[field], (int, float)
            ):
                return {}
        return data
    except (OSError, ValueError):
        return {}


def status_table(leagues: LeagueConfig, root: Path = STATUS_DIR) -> Table:
    from rich.table import Table

    table = Table(
        title="Scraper status (ET)",
        caption="Last scrape = completed attempt; Success = fetch + save completed.",
    )
    for heading in (
        "League",
        "Provider",
        "Worker",
        "Last result",
        "Last scrape",
        "Errors",
    ):
        table.add_column(heading)
    live_uptimes = []
    for provider, configured in (("espn", leagues.espn), ("sleeper", leagues.sleeper)):
        for name, league_id in configured.items():
            data = read_status(root / f"{provider}_{league_id}.json")
            state = str(data.get("status", "Not running"))
            if (
                data
                and state != "Stopped"
                and time.time() - data.get("heartbeat", 0) > STATUS_STALE_SECONDS
            ):
                state = "Stale / offline"
            seconds = int(data.get("uptime", 0))
            if data and state not in ("Stopped", "Stale / offline"):
                live_uptimes.append(seconds)
            table.add_row(
                name,
                provider,
                state,
                str(data.get("last_result", "--")),
                _eastern(data.get("last_scrape")),
                str(data.get("errors", 0)),
            )
    # Workers start together; the longest healthy worker is an approximate run uptime.
    if live_uptimes:
        seconds = max(live_uptimes)
        uptime = f"{seconds // 86400}d {seconds // 3600 % 24:02}:{seconds // 60 % 60:02}:{seconds % 60:02}"
        table.title = f"Scraper status (ET) | Worker uptime: ~{uptime}"
    return table


def _eastern(timestamp: float | None) -> str:
    return (
        datetime.fromtimestamp(timestamp, ZoneInfo("America/New_York")).strftime(
            "%m/%d %H:%M:%S"
        )
        if timestamp is not None
        else "--"
    )


def dashboard(leagues: LeagueConfig, root: Path = STATUS_DIR) -> Group:
    """Show cached windows only while every configured worker is healthy and idle."""
    from rich.console import Group
    from rich.table import Table
    from rich.text import Text

    from fantasy_football.scrapers.schedule.cache import read_cached_schedule
    from fantasy_football.scrapers.schedule.windows import (
        active_window,
        build_game_windows,
    )

    workers = [
        read_status(root / f"{provider}_{league_id}.json")
        for provider, configured in (
            ("espn", leagues.espn),
            ("sleeper", leagues.sleeper),
        )
        for league_id in configured.values()
    ]
    now = datetime.fromtimestamp(time.time(), timezone.utc)
    league_table = status_table(leagues, root)
    if not workers or not all(
        worker.get("status") == "Idle"
        and 0
        <= now.timestamp() - (worker.get("heartbeat") or 0)
        <= STATUS_STALE_SECONDS
        for worker in workers
    ):
        return Group(league_table)
    cached = read_cached_schedule()
    if cached is None:
        return Group(
            Text("Idle - schedule cache unavailable", style="dim"), league_table
        )
    games, updated = cached
    windows = build_game_windows(games)
    # Hide the schedule as soon as a window opens, even before workers wake up.
    if active_window(windows, now) is not None:
        return Group(league_table)
    upcoming = [window for window in windows if window.start > now]
    if not upcoming:
        return Group(
            Text("Idle ? no upcoming windows in cached schedule", style="dim"),
            league_table,
        )
    table = Table(
        title="Upcoming NFL windows (ET)",
        caption=f"Cached schedule updated: {_eastern(updated)} ET",
    )
    for heading in ("Week", "Games", "Opens (ET)", "Closes (ET)"):
        table.add_column(heading)
    eastern = ZoneInfo("America/New_York")
    for window in upcoming:
        table.add_row(
            ", ".join(map(str, window.nfl_weeks)) or "--",
            str(window.game_count),
            window.start.astimezone(eastern).strftime("%a %m/%d %I:%M %p"),
            window.end.astimezone(eastern).strftime("%a %m/%d %I:%M %p"),
        )
    return Group(table, Text(""), league_table)


def show_status(leagues: LeagueConfig, watch: bool = False) -> int:
    from rich.console import Console
    from rich.live import Live

    console = Console()
    if not watch:
        console.print(dashboard(leagues))
        return 0
    if not console.is_terminal:
        console.print(
            "--watch needs an interactive terminal; omit it for a single status table."
        )
        return 1
    try:
        with Live(dashboard(leagues), console=console, refresh_per_second=1) as live:
            while True:
                time.sleep(1)
                live.update(dashboard(leagues))
    except KeyboardInterrupt:
        return 0
