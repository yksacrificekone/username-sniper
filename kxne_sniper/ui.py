"""The dashboard — a rich Live terminal UI with animated banner, live CPS
sparkline, color-coded state machine and a scrolling event log."""
from __future__ import annotations

from collections import deque

from rich import box
from rich.align import Align
from rich.columns import Columns
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.sparkline import Sparkline
from rich.table import Table
from rich.text import Text

from . import __version__
from .stats import Stats

_STATE_STYLES = {
    "IDLE": "dim",
    "SEARCHING": "bold cyan",
    "ATTEMPTING CLAIM": "bold yellow",
    "SUCCESS": "bold green",
    "CLAIM FAILED": "bold red",
    "DONE": "bold blue",
}
_BANNER_COLORS = ["red", "yellow", "green", "cyan", "magenta", "blue"]


class Dashboard:
    def __init__(self, refresh_per_second: int = 8, active_getter=None):
        self.console = Console()
        self._live = Live(console=self.console, refresh_per_second=refresh_per_second, screen=True)
        self._frame = 0
        self._spark: deque[float] = deque(maxlen=60)
        self._active_getter = active_getter

    def __enter__(self) -> "Dashboard":
        self._live.__enter__()
        return self

    def __exit__(self, *exc) -> None:
        self._live.__exit__(*exc)

    def refresh(self, stats: Stats) -> None:
        self._frame += 1
        self._spark.append(stats.cps())
        self._live.update(self._render(stats))

    # ---- render pieces -------------------------------------------------
    def _banner(self) -> Text:
        text = Text()
        for i, ch in enumerate("KXNE SNIPER"):
            color = _BANNER_COLORS[(i + self._frame // 2) % len(_BANNER_COLORS)]
            text.append(ch, style=f"bold {color}")
        text.append("  ██▀▀▀▀▀█▀█▀█▀█▀", style="dim")
        return Align.center(text)

    def _status_line(self, stats: Stats) -> Text:
        style = _STATE_STYLES.get(stats.state, "dim")
        line = Text()
        line.append("● ", style=style)
        line.append(stats.state, style=style)
        line.append(f"   mode: {stats.mode or 'IDLE':<7}", style="bold white")
        if stats.target:
            line.append(f"   target: @{stats.target}", style="magenta")
        return Align.center(line)

    def _metrics_table(self, stats: Stats) -> Panel:
        table = Table(box=box.ROUNDED, show_header=False, pad_edge=False, expand=True)
        table.add_column("metric", style="dim")
        table.add_column("value", style="bold white", justify="right")
        table.add_row("Total checks", f"{stats.total_checks:,}")
        table.add_row("Available", f"[green]{stats.available:,}[/]")
        table.add_row("Taken", f"[red]{stats.taken:,}[/]")
        table.add_row("Errors", f"{stats.errors:,}")
        table.add_row("Rate limited", f"[yellow]{stats.rate_limited:,}[/]")
        table.add_row("Error rate", f"{stats.error_rate():.2f}%")
        table.add_row("CPS", f"[bold cyan]{stats.cps():.1f}[/]")
        table.add_row("Uptime", f"{int(stats.elapsed())}s")
        return Panel(table, title="[bold cyan]LIVE METRICS[/]", border_style="blue")

    def _state_table(self, stats: Stats) -> Panel:
        table = Table(box=box.ROUNDED, show_header=False, pad_edge=False, expand=True)
        table.add_column("key", style="dim")
        table.add_column("value", style="bold white", justify="right")
        table.add_row("Mode", f"[magenta]{stats.mode or 'IDLE'}[/]")
        table.add_row("Target", f"[white]@{stats.target}[/]" if stats.target else "[dim]—[/]")
        table.add_row("Pool workers", f"{stats.pool_size:,}")
        if self._active_getter is not None:
            table.add_row("Busy now", f"{self._active_getter():,}")
        table.add_row("Proxies", f"[yellow]{stats.proxy_count:,}[/]")
        table.add_row("Claims tried", f"{stats.claims_attempted}")
        table.add_row("Claims won", f"[green]{stats.claims_success}[/]")
        return Panel(table, title="[bold magenta]STATE[/]", border_style="magenta")

    def _spark_panel(self, stats: Stats) -> Panel:
        spark = Sparkline(list(self._spark), width=60, style="cyan")
        return Panel(spark, title=f"[bold cyan]THROUGHPUT[/] [dim]· last {len(self._spark)}s[/]",
                     border_style="cyan")

    def _events_panel(self, stats: Stats) -> Panel:
        lines = []
        for ts, text, style in list(stats.events)[-12:]:
            line = Text()
            line.append(f"[{ts}] ", style="dim")
            line.append(text, style=style)
            lines.append(line)
        if not lines:
            lines.append(Text("waiting for events…", style="dim"))
        return Panel(Group(*lines), title="[bold yellow]EVENT LOG[/]", border_style="yellow")

    def _footer(self, stats: Stats) -> Text:
        return Text(
            f"Ctrl+C to abort  •  kxne-sniper v{__version__}  •  "
            f"platform: {stats.mode and 'configured' or '—'}  •  state: {stats.state}",
            style="dim",
        )

    def _render(self, stats: Stats) -> Panel:
        left = self._metrics_table(stats)
        right = self._state_table(stats)
        body = Group(
            self._banner(),
            self._status_line(stats),
            Columns([left, right], equal=True, expand=True),
            self._spark_panel(stats),
            self._events_panel(stats),
            self._footer(stats),
        )
        return Panel(body, border_style="cyan",
                     title=f"[bold cyan] KXNE SNIPER — {stats.mode or 'IDLE'} [/]",
                     subtitle=f" v{__version__} ")
