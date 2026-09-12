"""Interactive local sync progress; redirected commands retain ordinary logs."""

from datetime import datetime
from threading import Lock
from zoneinfo import ZoneInfo

from rich.console import Console
from rich.live import Live
from rich.table import Table


class SyncDisplay:
    """Render one row per league, updating safely from download workers."""

    def __init__(self, targets: list[tuple[str, str, str]]) -> None:
        self.console = Console()
        self.enabled = self.console.is_terminal
        self.rows = {
            (p, str(i)): [p, n, "Waiting", "0", "--", "--"] for p, n, i in targets
        }
        self.lock = Lock()
        self.live = Live(console=self.console, refresh_per_second=4)

    def _table(self) -> Table:
        table = Table(title="League sync (ET)", expand=False)
        for heading in (
            "Provider",
            "League",
            "Status",
            "New files",
            "Last sync",
            "Latest snapshot",
        ):
            table.add_column(heading)
        for row in self.rows.values():
            table.add_row(*row)
        return table

    def __enter__(self) -> "SyncDisplay":
        if self.enabled:
            self.live.update(self._table())
            self.live.start()
        return self

    def __exit__(self, *args: object) -> None:
        if self.enabled:
            self.live.stop()

    def update(
        self, provider: str, league_id: str, status: str, count: int, latest: int | None
    ) -> None:
        if not self.enabled:
            return
        with self.lock:
            row = self.rows[(provider, str(league_id))]
            row[2] = status
            if status != "Failed":
                row[3] = str(count)
            if status == "Synced":
                row[4] = self._time(datetime.now().timestamp())
            if latest is not None:
                row[5] = self._time(latest)
            self.live.update(self._table())

    @staticmethod
    def _time(timestamp: float) -> str:
        return datetime.fromtimestamp(timestamp, ZoneInfo("America/New_York")).strftime(
            "%m/%d %H:%M:%S"
        )
