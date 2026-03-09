"""Shared animated install panel for long-running setup scripts.

Used by browser_cmd.py and n8n_cmd.py to show step-by-step progress
with a live-updating Rich panel while a setup script runs in a thread.
"""

from __future__ import annotations

import contextlib
import threading
import time
from collections.abc import Callable

from rich import box
from rich.live import Live
from rich.padding import Padding
from rich.panel import Panel

from arasul_tui.core.shell import run_cmd
from arasul_tui.core.theme import BAR_EMPTY, BAR_FILLED, DIM, PRIMARY, SUCCESS
from arasul_tui.core.ui.output import _adaptive_width, _frame_left_pad, console

# Spinner animation frames
SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

ICON_DONE = f"[{SUCCESS}]\u2713[/{SUCCESS}]"
ICON_PENDING = f"[{DIM}]\u25cb[/{DIM}]"


def build_install_panel(
    title: str,
    steps: list[tuple[str, str]],
    step_states: list[bool],
    active_step: int,
    frame_idx: int,
    elapsed: float,
    done: bool,
    failed: bool,
) -> Padding:
    """Build an animated installation panel with step progress."""
    lines: list[str] = [""]

    total = len(steps)
    if total == 0:
        return Padding("", (0, 0, 0, 0))
    completed = sum(step_states)

    for i, (label, detail) in enumerate(steps):
        if step_states[i]:
            icon = ICON_DONE
            line = f"  {icon}  [bold]{label}[/bold]  [{DIM}]{detail}[/{DIM}]"
        elif i == active_step and not done and not failed:
            frame = SPINNER_FRAMES[frame_idx % len(SPINNER_FRAMES)]
            icon = f"[{PRIMARY}]{frame}[/{PRIMARY}]"
            line = f"  {icon}  [bold]{label}[/bold]  [{DIM}]{detail}[/{DIM}]"
        else:
            icon = ICON_PENDING
            line = f"  {icon}  [{DIM}]{label}[/{DIM}]"
        lines.append(line)

    # Progress bar
    lines.append("")
    bar_w = 20
    fill = int(completed / total * bar_w)
    empty = bar_w - fill
    bar = f"[{PRIMARY}]{BAR_FILLED * fill}[/{PRIMARY}][{DIM}]{BAR_EMPTY * empty}[/{DIM}]"
    pct = int(completed / total * 100)

    mins = int(elapsed) // 60
    secs = int(elapsed) % 60
    time_str = f"{mins}:{secs:02d}" if mins else f"{secs}s"

    if failed:
        lines.append(f"  {bar}  [red]failed[/red]  [{DIM}]{time_str}[/{DIM}]")
    elif done:
        lines.append(f"  {bar}  [{SUCCESS}]complete[/{SUCCESS}]  [{DIM}]{time_str}[/{DIM}]")
    else:
        lines.append(f"  {bar}  [{DIM}]{pct}%  {time_str}[/{DIM}]")

    lines.append("")

    content = "\n".join(lines)
    panel_title = f"[bold]{title}[/bold]"
    if done:
        panel_title = f"[bold {SUCCESS}]{title}[/bold {SUCCESS}]"
    elif failed:
        panel_title = f"[bold red]{title}[/bold red]"

    panel_w = _adaptive_width() - 4
    left_pad = _frame_left_pad() + 2

    panel = Panel(
        content,
        title=panel_title,
        border_style=SUCCESS if done else ("red" if failed else DIM),
        box=box.ROUNDED,
        padding=(0, 1),
        width=panel_w,
    )
    return Padding(panel, (0, 0, 0, left_pad))


def run_install_animated(
    setup_cmd: str,
    title: str,
    steps: list[tuple[str, str]],
    check_milestone: Callable[[int], bool],
    is_success: Callable[[], bool],
) -> tuple[bool, str]:
    """Run a setup command with an animated progress display.

    Args:
        setup_cmd: Shell command to execute.
        title: Panel title (e.g. "Browser Setup", "n8n Setup").
        steps: List of (label, detail) tuples for each step.
        check_milestone: Callable(index) -> bool to poll step completion.
        is_success: Callable() -> bool to check overall success after script finishes.

    Returns:
        (success, output) tuple.
    """
    output = ""
    error: Exception | None = None
    done_event = threading.Event()

    def _worker() -> None:
        nonlocal output, error
        try:
            output = run_cmd(setup_cmd, timeout=600)
        except OSError as exc:
            error = exc
        finally:
            done_event.set()

    t = threading.Thread(target=_worker)
    t.start()

    step_states = [False] * len(steps)
    frame_idx = 0
    start_time = time.monotonic()

    with Live(
        build_install_panel(title, steps, step_states, 0, 0, 0, False, False),
        console=console,
        refresh_per_second=8,
        transient=False,
    ) as live:
        while not done_event.is_set():
            elapsed = time.monotonic() - start_time
            frame_idx += 1

            # Poll milestones
            for i in range(len(steps)):
                if not step_states[i]:
                    with contextlib.suppress(Exception):
                        step_states[i] = check_milestone(i)

            # Find active step (first incomplete)
            active = next(
                (i for i in range(len(steps)) if not step_states[i]),
                len(steps) - 1,
            )

            live.update(build_install_panel(title, steps, step_states, active, frame_idx, elapsed, False, False))
            time.sleep(0.12)

        # Final state — check all milestones one last time
        elapsed = time.monotonic() - start_time
        for i in range(len(steps)):
            if not step_states[i]:
                with contextlib.suppress(Exception):
                    step_states[i] = check_milestone(i)

        ok = error is None and is_success()
        live.update(
            build_install_panel(
                title,
                steps,
                step_states,
                len(steps) - 1,
                frame_idx,
                elapsed,
                done=ok,
                failed=not ok,
            )
        )

    if error:
        raise error
    return ok, output
