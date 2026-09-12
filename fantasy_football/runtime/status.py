"""Atomic worker heartbeats and status-file reads."""

from __future__ import annotations

import json
import logging
import tempfile
import time
from pathlib import Path
from threading import Event, Lock, Thread

from fantasy_football.constants import STATUS_DIR, STATUS_HEARTBEAT_SECONDS

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
