from __future__ import annotations

from arasul_tui.core.security import list_ssh_keys, recent_logins, security_audit
from arasul_tui.core.state import TuiState
from arasul_tui.core.types import CommandResult
from arasul_tui.core.ui import (
    content_width,
    print_checklist,
    print_info,
    print_styled_panel,
    suggest_next,
    truncate,
)

# ---------------------------------------------------------------------------
# /keys
# ---------------------------------------------------------------------------


def cmd_keys(state: TuiState, _: list[str]) -> CommandResult:
    """Show SSH key management."""
    keys = list_ssh_keys()
    if not keys:
        print_info("No SSH keys found in ~/.ssh/")
        suggest_next("Generate one: [bold]ssh-keygen -t ed25519[/bold]")
        return CommandResult(ok=True, style="silent")

    cw = content_width()
    rows: list[tuple[str, str]] = []
    for key in keys:
        label = key.type.replace("ssh-", "")
        detail = truncate(key.comment or key.path, cw)
        if key.bits:
            label += f" ({key.bits})"
        rows.append((label, detail))

    print_styled_panel("SSH Keys", rows)
    return CommandResult(ok=True, style="silent")


# ---------------------------------------------------------------------------
# /logins
# ---------------------------------------------------------------------------


def cmd_logins(state: TuiState, _: list[str]) -> CommandResult:
    """Show recent SSH logins."""
    cw = content_width()
    lines = recent_logins()
    rows: list[tuple[str, str]] = []
    for line in lines:
        parts = line.split(None, 2)
        if len(parts) >= 2:
            rows.append((parts[0], truncate(" ".join(parts[1:]), cw)))
        else:
            rows.append((truncate(line, cw), ""))

    print_styled_panel("Recent Logins", rows)
    return CommandResult(ok=True, style="silent")


# ---------------------------------------------------------------------------
# /security
# ---------------------------------------------------------------------------


def cmd_security(state: TuiState, _: list[str]) -> CommandResult:
    """Security audit checklist."""
    items = security_audit()
    checklist: list[tuple[str, str, str]] = [(i.label, i.detail, i.status) for i in items]
    print_checklist("Security Audit", checklist)
    fails = [i for i in items if i.status == "fail"]
    if fails:
        suggest_next("Fix issues: [bold]/setup[/bold] → Step 3 (SSH hardening)")
    return CommandResult(ok=True, style="silent")
