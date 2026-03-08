"""First-launch onboarding wizard."""

from __future__ import annotations

from pathlib import Path

from rich import box
from rich.padding import Padding
from rich.panel import Panel

from arasul_tui.core.platform import get_platform
from arasul_tui.core.types import CommandResult
from arasul_tui.core.ui import (
    _adaptive_width,
    _frame_left_pad,
    console,
    print_info,
    print_success,
)

ONBOARDING_FLAG = Path.home() / ".config" / "arasul" / ".onboarded"


def needs_onboarding() -> bool:
    """Check if this is the first launch."""
    return not ONBOARDING_FLAG.exists()


def mark_onboarded() -> None:
    """Mark onboarding as complete."""
    ONBOARDING_FLAG.parent.mkdir(parents=True, exist_ok=True)
    ONBOARDING_FLAG.touch()


def show_welcome() -> CommandResult:
    """Show welcome screen with hardware info and start onboarding."""
    platform = get_platform()

    content = "\n".join(
        [
            "",
            f"  Your [bold]{platform.display_name}[/bold] ({platform.ram_mb} MB RAM) is",
            "  ready for development.",
            "",
            "  Let's get you set up:",
            "",
            "  [bold]Step 1/3:[/bold]  What's your name?",
            "  [bold]Step 2/3:[/bold]  Set up Claude Code (AI pair programming)",
            "  [bold]Step 3/3:[/bold]  Create your first project",
            "",
        ]
    )

    w = _adaptive_width() - 4
    left_pad = _frame_left_pad() + 2
    panel = Panel(
        content,
        title="[bold cyan]Welcome to Arasul![/bold cyan]",
        border_style="cyan",
        box=box.ROUNDED,
        padding=(0, 1),
        width=w,
    )
    console.print(Padding(panel, (0, 0, 0, left_pad)), highlight=False)

    return CommandResult(
        ok=True,
        prompt="Press Enter to begin (or 'skip' to go to dashboard): ",
        pending_handler=_onboarding_ask_name,
        wizard_step=(1, 3, "Welcome"),
        style="wizard",
    )


def _onboarding_ask_name(state, raw):
    """Step 1: Ask for the user's first name."""
    if raw.strip().lower() in ("skip", "s", "q"):
        mark_onboarded()
        return CommandResult(ok=True, refresh=True, style="silent")

    print_info("")
    print_info("First, what should I call you?")

    return CommandResult(
        ok=True,
        prompt="Your first name: ",
        pending_handler=_onboarding_save_name,
        wizard_step=(1, 3, "Your Name"),
        style="wizard",
    )


def _onboarding_save_name(state, raw):
    """Save the user's name and proceed to Claude Code setup."""
    name = raw.strip()
    if name and name.lower() not in ("skip", "s", "q"):
        from arasul_tui.core.config import set_display_name

        set_display_name(name)
        state.display_name = name
        print_success(f"Nice to meet you, {name}!")
    elif name.lower() in ("skip", "s"):
        pass  # No name set, continue with setup

    return _show_step2_claude(state)


def _show_step2_claude(state):
    """Step 2: Claude Code authentication."""
    from arasul_tui.commands.ai import cmd_claude

    result = cmd_claude(state, [])

    if result.ok and not result.prompt:
        return _show_step3()

    if result.ok and result.pending_handler:
        original_handler = result.pending_handler

        def _chained(s, r):
            res = original_handler(s, r)
            if res.ok and not res.prompt:
                return _show_step3()
            return res

        return CommandResult(
            ok=True,
            prompt=result.prompt,
            pending_handler=_chained,
            wizard_step=(2, 3, "Claude Code"),
            style="wizard",
        )

    return result


def _show_step3():
    """Step 3: Create first project."""
    print_info("")
    print_success("Claude Code is configured!")
    print_info("")
    print_info("Now let's create your first project.")
    print_info("Give it a name (e.g., 'my-app', 'ml-experiment').")

    return CommandResult(
        ok=True,
        prompt="Project name (or 'skip'): ",
        pending_handler=_onboarding_step3_finish,
        wizard_step=(3, 3, "First Project"),
        style="wizard",
    )


def _onboarding_step3_finish(state, raw):
    """Finish step 3: create the project."""
    name = raw.strip()
    if not name or name.lower() in ("skip", "s", "q"):
        mark_onboarded()
        return CommandResult(ok=True, refresh=True, style="silent")

    from arasul_tui.commands.project import cmd_create

    result = cmd_create(state, [name])

    if result.ok:
        mark_onboarded()
        greeting = ""
        if state.display_name:
            greeting = f", {state.display_name}"
        print_info("")
        print_success(f"You're all set{greeting}!")
        print_info("")
        print_info("Quick tips:")
        print_info("  [bold]c[/bold]        Open Claude Code in this project")
        print_info("  [bold]help[/bold]     See all commands")
        print_info("  [bold]status[/bold]   Check system health")
        print_info("  [bold]1, 2...[/bold]  Switch between projects")
        print_info("")
        return CommandResult(ok=True, refresh=True, style="silent")

    return result
