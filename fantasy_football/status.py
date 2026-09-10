"""Best-effort worker heartbeats and an independently attachable dashboard."""

from __future__ import annotations

import json
import logging
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
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
        caption="Last scrape = completed attempt; Success = fetch + save completed. Uptime = worker runtime.",
    )
    for heading in (
        "League",
        "Provider",
        "Worker",
        "Last result",
        "Last scrape",
        "Last success",
        "Uptime",
        "Errors",
    ):
        table.add_column(heading)
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
            uptime = (
                f"{seconds // 86400}d {seconds // 3600 % 24:02}:{seconds // 60 % 60:02}:{seconds % 60:02}"
                if data
                else "--"
            )
            table.add_row(
                name,
                provider,
                state,
                str(data.get("last_result", "--")),
                _eastern(data.get("last_scrape")),
                _eastern(data.get("last_success")),
                uptime,
                str(data.get("errors", 0)),
            )
    return table


def _eastern(timestamp: float | None) -> str:
    return (
        datetime.fromtimestamp(timestamp, ZoneInfo("America/New_York")).strftime(
            "%m/%d %H:%M:%S"
        )
        if timestamp is not None
        else "--"
    )


def show_status(leagues: LeagueConfig, watch: bool = False) -> int:
    from rich.console import Console
    from rich.live import Live

    console = Console()
    if not watch:
        console.print(status_table(leagues))
        return 0
    if not console.is_terminal:
        console.print(
            "--watch needs an interactive terminal; omit it for a single status table."
        )
        return 1
    try:
        with Live(status_table(leagues), console=console, refresh_per_second=1) as live:
            while True:
                time.sleep(1)
                live.update(status_table(leagues))
    except KeyboardInterrupt:
        return 0
