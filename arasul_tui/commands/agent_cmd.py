"""Agent command — `/agent` and shortcut `a`.

Usage in TUI:
    a                            → prompt for task, then run multi-turn session
    a fix the login bug          → start session with task immediately
    /agent config                → show agent configuration
    /agent config model <name>   → set LLM model
    /agent config url <url>      → set Ollama base URL
    /agent config reset          → restore defaults

The agent runs in a blocking asyncio loop so the TUI pauses while the
agent works. After each task the user can give a follow-up or press Enter
to exit the session. Ctrl+C ends the session at any point.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from arasul_tui.agent.agent import AgentSession
from arasul_tui.agent.config import AgentConfig, _DEFAULTS, load_agent_config, save_agent_config
from arasul_tui.agent.ui.chat import ChatUI
from arasul_tui.core.state import TuiState
from arasul_tui.core.theme import DIM, PRIMARY, SUCCESS, WARNING
from arasul_tui.core.types import CommandResult
from arasul_tui.core.ui import console, content_pad, print_info, print_warning


def cmd_agent(state: TuiState, args: list[str]) -> CommandResult:
    """Start an interactive multi-turn agent session on the active project."""
    # --- config subcommand ---
    if args and args[0] == "config":
        return _cmd_agent_config(args[1:])

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
    """Run a multi-turn agent session synchronously (blocks the TUI loop)."""
    ui = ChatUI(project_path)
    cfg = load_agent_config()
    ui.print_header(task)
    try:
        asyncio.run(_multi_turn_loop(task, project_path, cfg, ui))
    except KeyboardInterrupt:
        console.print()
        pad = content_pad()
        console.print(f"{pad}[{DIM}]Session ended.[/{DIM}]")


async def _multi_turn_loop(
    first_task: str,
    project_path: Path,
    cfg: AgentConfig,
    ui: ChatUI,
) -> None:
    """Async loop: run the first task, then prompt for follow-ups until Enter."""
    session = AgentSession(
        project_path,
        config=cfg,
        callbacks=ui.make_callbacks(),
        approval=ui.ask_approval,
    )

    current_task = first_task
    while True:
        result = await session.run(current_task)
        ui.print_footer(result)

        next_task = await ui.ask_next_task()
        if next_task is None:
            break
        ui.print_separator(next_task)
        current_task = next_task


# ---------------------------------------------------------------------------
# /agent config
# ---------------------------------------------------------------------------

_CONFIG_HELP = (
    "Usage: agent config [show | model <name> | url <url> | num-ctx <n> | reset]"
)


def _cmd_agent_config(args: list[str]) -> CommandResult:
    cfg = load_agent_config()
    pad = content_pad()

    sub = args[0].lower() if args else "show"

    if sub == "show":
        console.print()
        console.print(f"{pad}[{PRIMARY}]◆ Agent Config[/{PRIMARY}]")
        console.print(f"{pad}  Model    [{DIM}]{cfg.model}[/{DIM}]")
        console.print(f"{pad}  URL      [{DIM}]{cfg.base_url}[/{DIM}]")
        console.print(f"{pad}  Context  [{DIM}]{cfg.context_limit} tokens (num_ctx: {cfg.num_ctx})[/{DIM}]")
        console.print(f"{pad}  Temp     [{DIM}]{cfg.temperature}[/{DIM}]")
        console.print()
        return CommandResult(ok=True, style="silent")

    if sub == "model" and len(args) >= 2:
        cfg.model = args[1]
        save_agent_config(cfg)
        console.print(f"{pad}[{SUCCESS}]✓[/{SUCCESS}] Model → [{DIM}]{cfg.model}[/{DIM}]")
        return CommandResult(ok=True, style="silent")

    if sub in ("url", "base-url") and len(args) >= 2:
        cfg.base_url = args[1]
        save_agent_config(cfg)
        console.print(f"{pad}[{SUCCESS}]✓[/{SUCCESS}] URL → [{DIM}]{cfg.base_url}[/{DIM}]")
        return CommandResult(ok=True, style="silent")

    if sub in ("num-ctx", "numctx", "ctx") and len(args) >= 2:
        try:
            cfg.num_ctx = int(args[1])
        except ValueError:
            print_warning(f"num-ctx must be an integer, got: {args[1]!r}")
            return CommandResult(ok=False, style="silent")
        save_agent_config(cfg)
        console.print(f"{pad}[{SUCCESS}]✓[/{SUCCESS}] num_ctx → [{DIM}]{cfg.num_ctx}[/{DIM}]")
        return CommandResult(ok=True, style="silent")

    if sub == "reset":
        defaults = _DEFAULTS
        cfg = AgentConfig(
            base_url=defaults["base_url"],
            model=defaults["model"],
            context_limit=defaults["context_limit"],
            num_ctx=defaults["num_ctx"],
            temperature=defaults["temperature"],
            max_output_tokens=defaults["max_output_tokens"],
            safe_command_prefixes=list(defaults["safe_command_prefixes"]),
        )
        save_agent_config(cfg)
        console.print(f"{pad}[{SUCCESS}]✓[/{SUCCESS}] Config reset to defaults.")
        return CommandResult(ok=True, style="silent")

    print_warning(f"Unknown option: {sub!r}")
    print_info(_CONFIG_HELP)
    return CommandResult(ok=False, style="silent")
