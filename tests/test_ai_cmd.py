from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from arasul_tui.commands.ai import (
    _auth_choice,
    _launch_inline,
    _wizard_step_account_info,
    _wizard_step_email,
    _wizard_step_token,
    cmd_auth,
    cmd_claude,
)
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


# ---------------------------------------------------------------------------
# Wizard step tests (10.1)
# ---------------------------------------------------------------------------


def test_wizard_step_token_invalid():
    state = _state()
    result = _wizard_step_token(state, "bad-token")
    assert result.ok is False
    assert result.pending_handler is _wizard_step_token


def test_wizard_step_token_valid():
    state = _state()
    result = _wizard_step_token(state, "sk-ant-oat01-valid-token")
    assert result.ok is True
    assert result.pending_handler is _wizard_step_account_info
    assert state._wizard_token == "sk-ant-oat01-valid-token"


def test_wizard_step_account_info_json_complete():
    state = _state()
    state._wizard_token = "sk-ant-oat01-test"
    json_input = '{"accountUuid": "abc-def-123", "emailAddress": "test@example.com"}'
    with patch("arasul_tui.commands.ai.save_claude_auth") as mock_save:
        result = _wizard_step_account_info(state, json_input)
    assert result.ok is True
    assert result.refresh is True
    mock_save.assert_called_once_with("sk-ant-oat01-test", "abc-def-123", "test@example.com")


def test_wizard_step_account_info_json_no_uuid():
    state = _state()
    state._wizard_token = "sk-ant-oat01-test"
    result = _wizard_step_account_info(state, '{"emailAddress": "x@y.com"}')
    assert result.ok is False
    assert result.pending_handler is _wizard_step_account_info


def test_wizard_step_account_info_json_no_email():
    state = _state()
    state._wizard_token = "sk-ant-oat01-test"
    result = _wizard_step_account_info(state, '{"accountUuid": "abc-123"}')
    assert result.ok is False
    assert result.pending_handler is _wizard_step_account_info


def test_wizard_step_account_info_json_token_missing():
    state = _state()
    state._wizard_token = ""
    json_input = '{"accountUuid": "abc-123", "emailAddress": "t@e.com"}'
    result = _wizard_step_account_info(state, json_input)
    assert result.ok is False
    assert result.pending_handler is None  # Terminal error, no retry


def test_wizard_step_account_info_invalid_json():
    state = _state()
    result = _wizard_step_account_info(state, "{broken json")
    assert result.ok is False
    assert result.pending_handler is _wizard_step_account_info


def test_wizard_step_account_info_plain_uuid():
    state = _state()
    result = _wizard_step_account_info(state, "abc-def-123-456")
    assert result.ok is True
    assert result.pending_handler is _wizard_step_email
    assert state._wizard_uuid == "abc-def-123-456"


def test_wizard_step_account_info_email_rejected():
    state = _state()
    result = _wizard_step_account_info(state, "user@example.com")
    assert result.ok is False


def test_wizard_step_account_info_short_uuid():
    state = _state()
    result = _wizard_step_account_info(state, "short")
    assert result.ok is False


def test_wizard_step_email_valid():
    state = _state()
    state._wizard_token = "sk-ant-oat01-test"
    state._wizard_uuid = "abc-123"
    with patch("arasul_tui.commands.ai.save_claude_auth") as mock_save:
        result = _wizard_step_email(state, "user@example.com")
    assert result.ok is True
    assert result.refresh is True
    mock_save.assert_called_once_with("sk-ant-oat01-test", "abc-123", "user@example.com")


def test_wizard_step_email_invalid():
    state = _state()
    result = _wizard_step_email(state, "not-an-email")
    assert result.ok is False
    assert result.pending_handler is _wizard_step_email


def test_wizard_step_email_state_lost():
    state = _state()
    state._wizard_token = ""
    state._wizard_uuid = ""
    result = _wizard_step_email(state, "user@example.com")
    assert result.ok is False


def test_auth_choice_1_starts_token_wizard():
    state = _state()
    result = _auth_choice(state, "1")
    assert result.ok is True
    assert result.pending_handler is _wizard_step_token


def test_auth_choice_2_browser_ok():
    state = _state()
    with patch("arasul_tui.commands.ai.ensure_browser", return_value=(True, "OK")):
        result = _auth_choice(state, "2")
    assert result.ok is True


def test_auth_choice_2_browser_missing():
    state = _state()
    with patch("arasul_tui.commands.ai.ensure_browser", return_value=(False, "Not installed")):
        result = _auth_choice(state, "2")
    assert result.ok is False


def test_auth_choice_3_manual():
    state = _state()
    result = _auth_choice(state, "3")
    assert result.ok is True


def test_auth_choice_invalid():
    state = _state()
    result = _auth_choice(state, "9")
    assert result.ok is False
    assert result.pending_handler is _auth_choice
