"""Styled panels, checklists, progress, key-value tables, and step headers."""

from __future__ import annotations

from rich import box
from rich.padding import Padding
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from arasul_tui.core.theme import (
    BAR_EMPTY,
    BAR_FILLED,
    DIM,
    ERROR,
    ICON_DOT_OFF,
    ICON_FAIL,
    ICON_OK,
    ICON_WARN,
    PRIMARY,
    WARNING,
)
from arasul_tui.core.ui.output import (
    _DOT,
    _adaptive_width,
    _frame_left_pad,
    _hline,
    console,
    content_pad,
)


def _vis_len(s: str) -> int:
    """Visible cell width of a string that may contain Rich markup."""
    try:
        return Text.from_markup(s).cell_len
    except Exception:
        # Malformed markup — fall back to plain length
        return len(s)


def _bar(pct: float, width: int = 10) -> str:
    """Render a modern block bar like ▰▰▰▱▱▱▱▱ with color based on percentage."""
    pct = max(0.0, min(100.0, pct))
    filled = int(round(pct / 100 * width))
    empty = width - filled
    if pct >= 90:
        color = ERROR
    elif pct >= 70:
        color = WARNING
    else:
        color = PRIMARY
    bar_filled = f"[{color}]{BAR_FILLED * filled}[/{color}]"
    bar_empty = f"[{DIM}]{BAR_EMPTY * empty}[/{DIM}]"
    return f"{bar_filled}{bar_empty}"


def print_styled_panel(title: str, rows: list[tuple[str, str]]) -> None:
    """Print a uniform styled panel with key-value rows."""
    w = _adaptive_width() - 4
    left_pad = _frame_left_pad() + 2
    table = Table(show_header=False, box=None, padding=(0, 2), expand=False)
    table.add_column(style="bold", no_wrap=True)
    table.add_column()
    for k, v in rows:
        table.add_row(k, v)
    p = Panel(table, title=f"[bold]{title}[/bold]", border_style="dim", box=box.ROUNDED, padding=(0, 1), width=w)
    console.print(Padding(p, (0, 0, 0, left_pad)), highlight=False)


def print_checklist(title: str, items: list[tuple[str, str, str]]) -> None:
    """Print a color-coded checklist. Items: (label, detail, status: ok/warn/fail)."""
    pad = content_pad()
    hline6 = _hline(6)
    console.print()
    console.print(f"{pad}[bold]{hline6} {title} {hline6}[/bold]", highlight=False)
    console.print()
    for label, detail, status in items:
        if status == "ok":
            icon = ICON_OK
        elif status == "warn":
            icon = ICON_WARN
        else:
            icon = ICON_FAIL
        console.print(f"{pad}   {icon}  [bold]{label}[/bold]       {detail}", highlight=False, soft_wrap=True)
    console.print()


def print_progress(title: str, items: list[tuple[str, bool]]) -> None:
    """Print a progress checklist. Items: (label, done)."""
    pad = content_pad()
    console.print()
    console.print(f"{pad}[bold]{title}[/bold]", highlight=False)
    console.print()
    for label, done in items:
        icon = ICON_OK if done else ICON_DOT_OFF
        style = "" if done else f"[{DIM}]"
        end_style = "" if done else f"[/{DIM}]"
        console.print(f"{pad}   {icon}  {style}{label}{end_style}", highlight=False)
    console.print()


def print_step(current: int, total: int, title: str) -> None:
    pad = content_pad()
    w = _adaptive_width() - 6
    step_suffix = f" {_DOT} Step {current}/{total} "
    # Truncate title if it would overflow the available width
    max_title = w - len(step_suffix) - 4  # 4 = minimum line chars (2 per side)
    if len(title) > max_title > 0:
        title = title[: max_title - 1] + "\u2026"
    title_plain = f" {title}{step_suffix}"
    title_len = len(title_plain)
    side = max(1, (w - title_len) // 2)
    right = max(1, w - title_len - side)
    left_line = _hline(side)
    right_line = _hline(right)
    console.print()
    console.print(
        f"{pad}[{PRIMARY}]{left_line}[/{PRIMARY}]"
        f" [bold]{title}[/bold] [{DIM}]{step_suffix.strip()}[/{DIM}] "
        f"[{PRIMARY}]{right_line}[/{PRIMARY}]",
        highlight=False,
    )
    console.print()


def print_kv(data: list[tuple[str, str]], title: str | None = None) -> None:
    w = _adaptive_width() - 4
    left_pad = _frame_left_pad() + 2
    table = Table(show_header=False, box=None, padding=(0, 2), expand=False)
    table.add_column(style="bold", no_wrap=True)
    table.add_column()
    for k, v in data:
        table.add_row(k, v)
    if title:
        p = Panel(table, title=f"[bold]{title}[/bold]", border_style="dim", box=box.ROUNDED, padding=(0, 1), width=w)
        console.print(Padding(p, (0, 0, 0, left_pad)), highlight=False)
    else:
        console.print(Padding(table, (0, 0, 0, left_pad)), highlight=False)
