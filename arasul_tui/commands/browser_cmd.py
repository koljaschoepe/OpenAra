"""Headless browser — /browser command handler.

Smart command that does the right thing based on current state:
- Chromium not installed -> animated install via 08-browser-setup.sh
- MCP not configured     -> auto-configure
- All good               -> show status panel

Only subcommand: /browser test
"""

from __future__ import annotations

import os
import shlex
from pathlib import Path

from arasul_tui.core.browser import (
    _find_chromium_binary,
    browser_health,
    browser_test,
    configure_mcp,
    is_chromium_installed,
    is_mcp_configured,
    is_playwright_installed,
)
from arasul_tui.core.shell import run_cmd
from arasul_tui.core.state import TuiState
from arasul_tui.core.types import CommandResult
from arasul_tui.core.ui import (
    console,
    content_pad,
    print_error,
    print_info,
    print_styled_panel,
    print_success,
    print_warning,
)
from arasul_tui.core.ui.animated_install import run_install_animated

# ---------------------------------------------------------------------------
# Animated install: step definitions + milestone checks
# ---------------------------------------------------------------------------


def _browser_cache_dir() -> Path:
    """Return the expected browser cache directory."""
    from arasul_tui.core.browser import _storage_browser_cache

    return _storage_browser_cache()


def _check_milestone(index: int) -> bool:
    """Check if a milestone is reached by polling filesystem."""
    if index == 0:  # System deps (apt packages installed)
        out = run_cmd("dpkg -l libatk-bridge2.0-0 2>/dev/null | grep -c '^ii'", timeout=3)
        return bool(out and out.strip().isdigit() and int(out.strip()) > 0)
    if index == 1:  # Playwright Python package
        return is_playwright_installed()
    if index == 2:  # Browser cache directory
        return _browser_cache_dir().exists()
    if index == 3:  # Chromium binary downloaded
        return _find_chromium_binary() is not None
    if index == 4:  # MCP configured
        return is_mcp_configured()
    return False


def _steps() -> list[tuple[str, str]]:
    return [
        ("System dependencies", "apt packages"),
        ("Playwright", "Python package"),
        ("Browser cache", str(_browser_cache_dir())),
        ("Chromium", "headless browser (~180 MB)"),
        ("MCP server", "Claude integration"),
    ]


# ---------------------------------------------------------------------------
# Status panel
# ---------------------------------------------------------------------------


def _show_status() -> CommandResult:
    rows = browser_health()
    print_styled_panel("Browser", rows)
    return CommandResult(ok=True, style="silent")


# ---------------------------------------------------------------------------
# Smart flow: install -> mcp -> status
# ---------------------------------------------------------------------------


def _smart_flow() -> CommandResult:
    # --- Step 1: Install if Chromium missing ---
    if not is_chromium_installed():
        script = run_cmd("command -v sudo 2>/dev/null", timeout=2)
        if not script:
            print_error("sudo not available.")
            return CommandResult(ok=False, style="silent")

        repo_root = Path(__file__).parent.parent.parent
        setup_script = repo_root / "scripts" / "08-browser-setup.sh"
        if not setup_script.exists():
            print_error("Setup script not found.")
            print_info("Run manually: [bold]sudo ./setup.sh --step 8[/bold]")
            return CommandResult(ok=False, style="silent")

        from arasul_tui.core.platform import get_platform

        mount = get_platform().storage.mount
        real_user = os.environ.get("USER") or os.environ.get("LOGNAME", "")
        env_vars = (
            f"STORAGE_MOUNT={shlex.quote(str(mount))}"
            f" NVME_MOUNT={shlex.quote(str(mount))}"
            f" REAL_USER={shlex.quote(real_user)}"
            f" SCRIPT_DIR={shlex.quote(str(repo_root))}"
        )

        console.print()
        try:
            ok, output = run_install_animated(
                f"sudo env {env_vars} bash {shlex.quote(str(setup_script))} 2>&1",
                title="Browser Setup",
                steps=_steps(),
                check_milestone=_check_milestone,
                is_success=is_chromium_installed,
            )
        except OSError as exc:
            print_error(f"Installation failed: {exc}")
            return CommandResult(ok=False, style="silent")

        if not ok:
            print_warning("Browser installation may have failed.")
            if output:
                pad = content_pad()
                console.print(f"{pad}[dim]{output[-500:]}[/dim]", highlight=False)
            print_info("Try again: [bold]/browser[/bold] or check [dim]/var/log/arasul/[/dim]")
            return CommandResult(ok=False, style="silent")

        console.print()
        print_success("Playwright + Chromium installed!")

    # --- Step 2: Configure MCP if missing ---
    if not is_mcp_configured():
        try:
            ok, msg = configure_mcp()
            if ok:
                print_success(msg)
            else:
                print_warning(f"MCP config failed: {msg}")
        except OSError as exc:
            print_warning(f"MCP config failed: {exc}")

    # --- Step 3: Show status ---
    return _show_status()


# ---------------------------------------------------------------------------
# /browser test
# ---------------------------------------------------------------------------


def _do_test() -> CommandResult:
    ok, lines = browser_test()
    for line in lines:
        (print_success if ok else print_error)(line)
    return CommandResult(ok=ok, style="silent")


# ---------------------------------------------------------------------------
# /browser (dispatcher)
# ---------------------------------------------------------------------------


def cmd_browser(state: TuiState, args: list[str]) -> CommandResult:
    if args and args[0].lower() == "test":
        return _do_test()

    return _smart_flow()
