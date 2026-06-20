"""First-launch onboarding — name + server URL setup."""

from __future__ import annotations

from pathlib import Path

from arasul_tui.core.config import get_display_name
from arasul_tui.core.types import CommandResult
from arasul_tui.core.ui import console, content_pad, print_success

ONBOARDING_FLAG = Path.home() / ".config" / "arasul" / ".onboarded"


def needs_onboarding() -> bool:
    return not ONBOARDING_FLAG.exists()


def mark_onboarded() -> None:
    try:
        ONBOARDING_FLAG.parent.mkdir(parents=True, exist_ok=True)
        ONBOARDING_FLAG.touch()
    except OSError:
        pass


def _agent_url_is_default() -> bool:
    """Return True if the agent URL has never been changed from the default."""
    from arasul_tui.agent.config import load_agent_config
    cfg = load_agent_config()
    return cfg.base_url == "http://localhost:11434/v1"


def show_welcome() -> CommandResult:
    """First launch: ask name, then optionally server URL."""
    if get_display_name():
        # Name already known — go straight to URL step if needed
        if _agent_url_is_default():
            return _ask_server_url()
        mark_onboarded()
        return CommandResult(ok=True, refresh=True, style="silent")

    return CommandResult(
        ok=True,
        prompt="Your name (Enter to skip): ",
        pending_handler=_save_name,
        style="wizard",
    )


def _save_name(state, raw: str) -> CommandResult:
    name = raw.strip()
    if name and name.lower() not in ("skip", "s", "q", ""):
        from arasul_tui.core.config import set_display_name
        set_display_name(name)
        state.display_name = name
        print_success(f"Welcome, {name}!")

    # After name: check if URL needs setting
    if _agent_url_is_default():
        return _ask_server_url()

    mark_onboarded()
    return CommandResult(ok=True, refresh=True, style="silent")


def _ask_server_url() -> CommandResult:
    """Prompt for Ollama server URL."""
    pad = content_pad()
    console.print()
    console.print(f"{pad}[bold]Connect to Ollama[/bold]")
    console.print(f"{pad}[dim]Default assumes Ollama runs locally on this machine.[/dim]")
    console.print()
    return CommandResult(
        ok=True,
        prompt="Ollama URL [http://localhost:11434/v1]: ",
        pending_handler=_save_server_url,
        style="wizard",
    )


def _save_server_url(state, raw: str) -> CommandResult:
    import asyncio
    from arasul_tui.agent.config import load_agent_config, save_agent_config
    from arasul_tui.agent.llm import check_connection
    from arasul_tui.core.theme import DIM, ERROR, SUCCESS, WARNING
    from arasul_tui.core.ui import console, content_pad

    url = raw.strip() or "http://localhost:11434/v1"
    pad = content_pad()

    cfg = load_agent_config()
    cfg.base_url = url
    save_agent_config(cfg)

    # Quick connection test
    console.print(f"{pad}[{DIM}]Testing {url} …[/{DIM}]")
    try:
        result = asyncio.run(check_connection(url, timeout=6.0))
        if result["ok"]:
            models = "  ·  ".join(result["models"][:4])
            console.print(f"{pad}[{SUCCESS}]✓[/{SUCCESS}]  Connected ({result['latency_ms']}ms)")
            console.print(f"{pad}   Models: [{DIM}]{models}[/{DIM}]")
        else:
            console.print(f"{pad}[{WARNING}]![/{WARNING}]  {result['error']}")
            console.print(f"{pad}[{DIM}]   URL saved. Fix later with: agent config url <url>[/{DIM}]")
    except Exception as exc:
        console.print(f"{pad}[{ERROR}]✗[/{ERROR}]  {exc}")
        console.print(f"{pad}[{DIM}]   URL saved. Fix later with: agent config url <url>[/{DIM}]")

    console.print()
    mark_onboarded()
    return CommandResult(ok=True, refresh=True, style="silent")
