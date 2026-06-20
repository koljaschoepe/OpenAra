"""Agent command — `/agent` and shortcut `a`.

Usage in TUI:
    a                     → prompt for task, then run agent
    a fix the login bug   → run agent immediately with task
    /agent read main.py   → same, slash-style

The agent runs in a blocking asyncio loop so the TUI pauses while the
agent works. On KeyboardInterrupt, the session ends gracefully.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from arasul_tui.agent.agent import run_agent
from arasul_tui.agent.config import load_agent_config
from arasul_tui.agent.ui.chat import ChatUI
from arasul_tui.core.state import TuiState
from arasul_tui.core.types import CommandResult
from arasul_tui.core.ui import console, content_pad, print_info, print_warning


def cmd_agent(state: TuiState, args: list[str]) -> CommandResult:
    """Start an agent session on the active project.

    With args: use them as the task directly.
    Without args: prompt for a task (single-line for now).
    """
    if not state.active_project:
        print_warning("No active project.")
        print_info("Open a project first — type its name or number.")
        return CommandResult(ok=False, style="silent")

    if args:
        task = " ".join(args).strip()
        if task:
            _run_session(task, state.active_project)
            return CommandResult(ok=True, style="silent")

    # No task provided → ask via pending_handler
    return CommandResult(
        ok=True,
        style="silent",
        prompt="Task",
        pending_handler=_agent_task_handler,
    )


def _agent_task_handler(state: TuiState, user_input: str) -> CommandResult:
    task = user_input.strip()
    if not task:
        print_info("No task provided.")
        return CommandResult(ok=True, style="silent")
    if not state.active_project:
        print_warning("Active project disappeared — please re-open.")
        return CommandResult(ok=False, style="silent")
    _run_session(task, state.active_project)
    return CommandResult(ok=True, style="silent", refresh=True)


def _run_session(task: str, project_path: Path) -> None:
    """Run one agent session synchronously (blocks the TUI loop)."""
    ui = ChatUI(project_path)
    cfg = load_agent_config()

    ui.print_header(task)

    try:
        result = asyncio.run(
            run_agent(
                task=task,
                project_path=project_path,
                config=cfg,
                callbacks=ui.make_callbacks(),
                approval=ui.ask_approval,
            )
        )
    except KeyboardInterrupt:
        console.print()
        pad = content_pad()
        console.print(f"{pad}[dim]Agent interrupted.[/dim]")
        return

    ui.print_footer(result)
