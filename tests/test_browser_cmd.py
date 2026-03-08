from __future__ import annotations

from unittest.mock import patch

from arasul_tui.commands.browser_cmd import cmd_browser
from arasul_tui.core.router import REGISTRY
from arasul_tui.core.state import TuiState


def _state() -> TuiState:
    return TuiState(registry=REGISTRY)


# --- Smart flow tests ---


def test_browser_not_installed_triggers_install():
    """When Chromium is missing, the smart flow should attempt installation."""
    with (
        patch("arasul_tui.commands.browser_cmd.is_chromium_installed", side_effect=[False, True]),
        patch("arasul_tui.commands.browser_cmd.run_cmd", return_value="/usr/bin/sudo"),
        patch("arasul_tui.commands.browser_cmd.run_install_animated", return_value=(True, "ok")),
        patch("arasul_tui.commands.browser_cmd.is_mcp_configured", return_value=True),
        patch("arasul_tui.commands.browser_cmd.browser_health", return_value=[("Chromium", "ok")]),
        patch("arasul_tui.commands.browser_cmd.Path") as mock_path,
    ):
        mock_path.return_value.parent.parent.parent = mock_path
        mock_script = mock_path.__truediv__.return_value.__truediv__.return_value
        mock_script.exists.return_value = True
        result = cmd_browser(_state(), [])
    assert result.ok is True


def test_browser_installed_no_mcp_configures():
    """When Chromium is installed but MCP missing, auto-configure MCP."""
    with (
        patch("arasul_tui.commands.browser_cmd.is_chromium_installed", return_value=True),
        patch("arasul_tui.commands.browser_cmd.is_mcp_configured", return_value=False),
        patch("arasul_tui.commands.browser_cmd.configure_mcp", return_value=(True, "MCP OK")) as mock_mcp,
        patch("arasul_tui.commands.browser_cmd.browser_health", return_value=[("Chromium", "ok")]),
    ):
        result = cmd_browser(_state(), [])
    assert result.ok is True
    mock_mcp.assert_called_once()


def test_browser_all_ok_shows_status():
    """When everything is installed, just show status."""
    rows = [("Playwright", "[green]✓[/green] installed"), ("Chromium", "[green]✓[/green] installed")]
    with (
        patch("arasul_tui.commands.browser_cmd.is_chromium_installed", return_value=True),
        patch("arasul_tui.commands.browser_cmd.is_mcp_configured", return_value=True),
        patch("arasul_tui.commands.browser_cmd.browser_health", return_value=rows),
    ):
        result = cmd_browser(_state(), [])
    assert result.ok is True
    assert result.style == "silent"


def test_browser_install_no_sudo():
    """When sudo is not available, installation should fail."""
    with (
        patch("arasul_tui.commands.browser_cmd.is_chromium_installed", return_value=False),
        patch("arasul_tui.commands.browser_cmd.run_cmd", return_value=""),
    ):
        result = cmd_browser(_state(), [])
    assert result.ok is False


# --- Test subcommand ---


def test_browser_test_ok():
    with patch("arasul_tui.commands.browser_cmd.browser_test", return_value=(True, ["OK"])):
        result = cmd_browser(_state(), ["test"])
    assert result.ok is True


def test_browser_test_fail():
    with patch("arasul_tui.commands.browser_cmd.browser_test", return_value=(False, ["Fail"])):
        result = cmd_browser(_state(), ["test"])
    assert result.ok is False


# --- Default is smart flow (not status) ---


def test_browser_default_is_smart_flow():
    """No args should run smart flow, not just status."""
    rows = [("Playwright", "[green]✓[/green] installed")]
    with (
        patch("arasul_tui.commands.browser_cmd.is_chromium_installed", return_value=True),
        patch("arasul_tui.commands.browser_cmd.is_mcp_configured", return_value=True),
        patch("arasul_tui.commands.browser_cmd.browser_health", return_value=rows),
    ):
        result = cmd_browser(_state(), [])
    assert result.ok is True
