from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from arasul_tui.commands.ai import _launch_inline, cmd_auth, cmd_claude
from arasul_tui.core.router import REGISTRY
from arasul_tui.core.state import TuiState


def _state(project: Path | None = None) -> TuiState:
    s = TuiState(registry=REGISTRY)
    if project:
        s.active_project = project
    return s


def test_launch_inline_no_project():
    result = _launch_inline(_state(), "claude")
    assert result.ok is False


def test_launch_inline_not_installed(tmp_path: Path):
    with patch("arasul_tui.commands.ai.shutil") as mock_shutil:
        mock_shutil.which.return_value = None
        result = _launch_inline(_state(tmp_path), "claude")
    assert result.ok is False


def test_launch_inline_success(tmp_path: Path):
    with patch("arasul_tui.commands.ai.shutil") as mock_shutil:
        mock_shutil.which.return_value = "/usr/bin/claude"
        result = _launch_inline(_state(tmp_path), "claude")
    assert result.ok is True
    assert result.quit_app is True
    assert result.launch_command == "claude"


def test_cmd_claude_not_configured():
    with patch("arasul_tui.commands.ai.is_claude_configured", return_value=False):
        result = cmd_claude(_state(), [])
    assert result.ok is True
    assert result.pending_handler is not None  # Wizard started


def test_cmd_claude_configured_no_project():
    with (
        patch("arasul_tui.commands.ai.is_claude_configured", return_value=True),
        patch("arasul_tui.commands.ai.shutil") as mock_shutil,
    ):
        mock_shutil.which.return_value = None
        result = cmd_claude(_state(), [])
    assert result.ok is False  # No active project


def test_cmd_auth_all_configured():
    with (
        patch("arasul_tui.commands.ai.is_claude_configured", return_value=True),
        patch("arasul_tui.commands.ai.run_cmd", return_value="Logged in as user"),
        patch("arasul_tui.commands.ai.parse_gh_account", return_value="user"),
        patch("arasul_tui.core.browser.ensure_browser", return_value=(True, "OK")),
        patch("arasul_tui.core.browser.is_mcp_configured", return_value=True),
    ):
        result = cmd_auth(_state(), [])
    assert result.ok is True


def test_cmd_auth_nothing_configured():
    with (
        patch("arasul_tui.commands.ai.is_claude_configured", return_value=False),
        patch("arasul_tui.commands.ai.run_cmd", return_value=""),
        patch("arasul_tui.core.browser.ensure_browser", return_value=(False, "Not installed")),
        patch("arasul_tui.core.browser.is_mcp_configured", return_value=False),
    ):
        result = cmd_auth(_state(), [])
    assert result.ok is True
