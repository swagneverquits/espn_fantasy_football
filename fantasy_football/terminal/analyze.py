"""Interactive analysis progress display."""

from threading import Lock

from rich.console import Console
from rich.live import Live
from rich.table import Table


class AnalyzeDisplay:
    """Render one live analysis row per league."""

    def __init__(self, targets: list[tuple[str, str, str]]) -> None:
        self.console = Console()
        self.enabled = self.console.is_terminal
        self.rows = {
            (provider, str(league_id)): [
                provider,
                name,
                "Running",
                "--",
                "--",
                "--",
                "--",
            ]
            for provider, name, league_id in targets
        }
        self.lock = Lock()
        # PowerShell can render normal Live cursor-up refreshes as appended
        # output. Alternate-screen mode gives the dashboard a stable surface.
        self.live = Live(
            console=self.console,
            refresh_per_second=4,
            screen=True,
            transient=True,
        )

    def _table(self) -> Table:
        table = Table(title="Matchup analysis", expand=False)
        for heading in (
            "Provider",
            "League",
            "Status",
            "Rows",
            "Load",
            "Plots",
            "Render",
        ):
            table.add_column(heading)
        for row in self.rows.values():
            table.add_row(*row)
        return table

    def final_table(self) -> Table:
        """Return the final table for persistent output after Live exits."""
        return self._table()

    def __enter__(self) -> "AnalyzeDisplay":
        if self.enabled:
            self.live.update(self._table())
            self.live.start()
        return self

    def __exit__(self, *args: object) -> None:
        if self.enabled:
            self.live.stop()

    def update(
        self,
        provider: str,
        league_id: str,
        status: str,
        *,
        rows: int | None = None,
        load_seconds: float | None = None,
        plots: int | None = None,
        render_seconds: float | None = None,
    ) -> None:
        if not self.enabled:
            return
        with self.lock:
            row = self.rows[(provider, str(league_id))]
            row[2] = status
            if rows is not None:
                row[3] = str(rows)
            if load_seconds is not None:
                row[4] = f"{load_seconds:.2f}s"
            if plots is not None:
                row[5] = str(plots)
            if render_seconds is not None:
                row[6] = f"{render_seconds:.2f}s"
            self.live.update(self._table())
