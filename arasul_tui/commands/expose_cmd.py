"""Tailscale Funnel management for webapp projects."""

from __future__ import annotations

import subprocess

from arasul_tui.core.state import TuiState
from arasul_tui.core.types import CommandResult
from arasul_tui.core.ui import (
    print_error,
    print_info,
    print_styled_panel,
    print_success,
    spinner_run,
)


def _run(cmd: list[str], timeout: int = 10) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _is_tailscale_running() -> bool:
    try:
        result = _run(["tailscale", "status"])
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _get_funnel_status() -> list[tuple[str, str]]:
    """Get current Tailscale Funnel status."""
    try:
        result = _run(["tailscale", "funnel", "status"])
        if result.returncode != 0:
            return []
        lines = []
        for line in (result.stdout or "").strip().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                lines.append(("Route", line))
        return lines
    except (OSError, subprocess.TimeoutExpired):
        return []


def cmd_expose(state: TuiState, args: list[str]) -> CommandResult:
    """Manage Tailscale Funnel (status works without active project)."""
    sub = args[0].lower() if args else "status"

    if sub == "status":
        if not _is_tailscale_running():
            print_error("Tailscale is not running.")
            print_info("Start it with [bold]/tailscale up[/bold]")
            return CommandResult(ok=False, style="silent")

        routes = _get_funnel_status()
        if routes:
            print_styled_panel("Funnel Status", routes)
        else:
            print_info("No active Funnel routes.")
            print_info("Start with [bold]/expose on[/bold]")
        return CommandResult(ok=True, style="silent")

    elif sub == "on":
        port = args[1] if len(args) > 1 else "3000"
        if not _is_tailscale_running():
            print_error("Tailscale is not running.")
            return CommandResult(ok=False, style="silent")

        def _start() -> subprocess.CompletedProcess[str]:
            return _run(["tailscale", "funnel", "--bg", port], timeout=30)

        try:
            result = spinner_run(f"Starting Funnel on port {port}...", _start)
        except (subprocess.TimeoutExpired, OSError) as exc:
            print_error(f"Failed: {exc}")
            return CommandResult(ok=False, style="silent")

        if result.returncode == 0:
            output = (result.stdout or "").strip()
            print_success(f"Funnel active on port {port}")
            if output:
                print_info(output)
        else:
            err = (result.stderr or result.stdout or "").strip()
            print_error(f"Funnel failed: {err}")
            return CommandResult(ok=False, style="silent")
        return CommandResult(ok=True, style="silent")

    elif sub == "off":

        def _stop() -> subprocess.CompletedProcess[str]:
            return _run(["tailscale", "funnel", "--bg", "off"], timeout=15)

        try:
            result = spinner_run("Stopping Funnel...", _stop)
        except (subprocess.TimeoutExpired, OSError) as exc:
            print_error(f"Failed: {exc}")
            return CommandResult(ok=False, style="silent")

        if result.returncode == 0:
            print_success("Funnel stopped")
            return CommandResult(ok=True, style="silent")
        else:
            err = (result.stderr or result.stdout or "").strip()
            print_error(f"Stop failed: {err}")
            return CommandResult(ok=False, style="silent")

    else:
        print_info("Usage: [bold]/expose[/bold] [dim]status|on|off[/dim]")
        return CommandResult(ok=False, style="silent")
