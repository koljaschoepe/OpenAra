"""First-launch onboarding — minimal name prompt, no wizard."""

from __future__ import annotations

from pathlib import Path

from arasul_tui.core.config import get_display_name
from arasul_tui.core.types import CommandResult
from arasul_tui.core.ui import print_success

ONBOARDING_FLAG = Path.home() / ".config" / "arasul" / ".onboarded"


def needs_onboarding() -> bool:
    """Check if this is the first launch."""
    return not ONBOARDING_FLAG.exists()


def mark_onboarded() -> None:
    """Mark onboarding as complete."""
    try:
        ONBOARDING_FLAG.parent.mkdir(parents=True, exist_ok=True)
        ONBOARDING_FLAG.touch()
    except OSError:
        pass


def show_welcome() -> CommandResult:
    """First launch: ask for name if unknown, then done."""
    if get_display_name():
        mark_onboarded()
        return CommandResult(ok=True, refresh=True, style="silent")

    return CommandResult(
        ok=True,
        prompt="What's your name? ",
        pending_handler=_save_name,
        style="wizard",
    )


def _save_name(state, raw):
    """Save name and finish onboarding."""
    name = raw.strip()
    if name and name.lower() not in ("skip", "s", "q"):
        from arasul_tui.core.config import set_display_name

        set_display_name(name)
        state.display_name = name
        print_success(f"Welcome, {name}!")

    mark_onboarded()
    return CommandResult(ok=True, refresh=True, style="silent")
