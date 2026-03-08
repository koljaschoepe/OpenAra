from __future__ import annotations

from unittest.mock import MagicMock, patch

from arasul_tui.core.onboarding import (
    _onboarding_save_name,
    _onboarding_skip_to_claude,
    _onboarding_step3_finish,
    mark_onboarded,
    needs_onboarding,
    show_welcome,
)
from arasul_tui.core.router import REGISTRY
from arasul_tui.core.state import TuiState


def _state() -> TuiState:
    return TuiState(registry=REGISTRY)


def test_needs_onboarding_true(tmp_path, monkeypatch):
    monkeypatch.setattr("arasul_tui.core.onboarding.ONBOARDING_FLAG", tmp_path / ".onboarded")
    assert needs_onboarding() is True


def test_needs_onboarding_false(tmp_path, monkeypatch):
    flag = tmp_path / ".onboarded"
    flag.touch()
    monkeypatch.setattr("arasul_tui.core.onboarding.ONBOARDING_FLAG", flag)
    assert needs_onboarding() is False


def test_mark_onboarded(tmp_path, monkeypatch):
    flag = tmp_path / "config" / "arasul" / ".onboarded"
    monkeypatch.setattr("arasul_tui.core.onboarding.ONBOARDING_FLAG", flag)
    mark_onboarded()
    assert flag.exists()


@patch("arasul_tui.core.onboarding.get_platform")
@patch("arasul_tui.core.onboarding.get_display_name", return_value="")
def test_show_welcome_no_name(mock_name, mock_platform):
    """First launch without known name asks for name directly."""
    mock_platform.return_value = MagicMock(display_name="Test Device", ram_mb=4096)
    result = show_welcome()
    assert result.ok is True
    assert "first name" in result.prompt.lower()
    assert result.pending_handler == _onboarding_save_name
    assert result.style == "wizard"


@patch("arasul_tui.core.onboarding.get_platform")
@patch("arasul_tui.core.onboarding.get_display_name", return_value="Kolja")
def test_show_welcome_name_known(mock_name, mock_platform):
    """When name is already known, skip name step and go to Claude."""
    mock_platform.return_value = MagicMock(display_name="Test Device", ram_mb=4096)
    result = show_welcome()
    assert result.ok is True
    assert result.pending_handler == _onboarding_skip_to_claude
    assert result.wizard_step == (1, 2, "Welcome")


@patch("arasul_tui.core.onboarding.mark_onboarded")
def test_skip_to_claude_skip(mock_mark):
    result = _onboarding_skip_to_claude(_state(), "skip")
    assert result.ok is True
    assert result.refresh is True
    mock_mark.assert_called_once()


@patch("arasul_tui.core.onboarding._show_step2_claude")
def test_skip_to_claude_enter(mock_step2):
    from arasul_tui.core.types import CommandResult

    mock_step2.return_value = CommandResult(ok=True, style="silent")
    _onboarding_skip_to_claude(_state(), "")
    mock_step2.assert_called_once()


@patch("arasul_tui.core.onboarding._show_step2_claude")
@patch("arasul_tui.core.config.set_display_name")
def test_save_name(mock_set, mock_step2):
    from arasul_tui.core.types import CommandResult

    mock_step2.return_value = CommandResult(ok=True, style="silent")
    state = _state()
    _onboarding_save_name(state, "Kolja")
    mock_set.assert_called_once_with("Kolja")
    assert state.display_name == "Kolja"
    mock_step2.assert_called_once()


@patch("arasul_tui.core.onboarding.mark_onboarded")
def test_save_name_skip(mock_mark):
    result = _onboarding_save_name(_state(), "skip")
    assert result.ok is True
    assert result.refresh is True
    mock_mark.assert_called_once()


@patch("arasul_tui.core.onboarding.mark_onboarded")
def test_step3_skip(mock_mark):
    result = _onboarding_step3_finish(_state(), "skip")
    assert result.ok is True
    assert result.refresh is True
    mock_mark.assert_called_once()


@patch("arasul_tui.core.onboarding.mark_onboarded")
def test_step3_empty_input(mock_mark):
    result = _onboarding_step3_finish(_state(), "")
    assert result.ok is True
    mock_mark.assert_called_once()


@patch("arasul_tui.core.onboarding.mark_onboarded")
@patch("arasul_tui.commands.project.cmd_create")
def test_step3_creates_project(mock_create, mock_mark):
    from arasul_tui.core.types import CommandResult

    mock_create.return_value = CommandResult(ok=True, style="silent")
    result = _onboarding_step3_finish(_state(), "my-project")
    mock_create.assert_called_once()
    assert result.ok is True
    mock_mark.assert_called_once()
