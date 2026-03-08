from __future__ import annotations

from unittest.mock import patch

from arasul_tui.core.onboarding import (
    _save_name,
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


@patch("arasul_tui.core.onboarding.get_display_name", return_value="")
def test_show_welcome_no_name(mock_name):
    """First launch without known name asks for name."""
    result = show_welcome()
    assert result.ok is True
    assert result.prompt == "What's your name? "
    assert result.pending_handler == _save_name


@patch("arasul_tui.core.onboarding.mark_onboarded")
@patch("arasul_tui.core.onboarding.get_display_name", return_value="Kolja")
def test_show_welcome_name_known(mock_name, mock_mark):
    """When name is already known, just mark onboarded and refresh."""
    result = show_welcome()
    assert result.ok is True
    assert result.refresh is True
    assert result.prompt is None
    mock_mark.assert_called_once()


@patch("arasul_tui.core.onboarding.mark_onboarded")
@patch("arasul_tui.core.config.set_display_name")
def test_save_name(mock_set, mock_mark):
    state = _state()
    _save_name(state, "Kolja")
    mock_set.assert_called_once_with("Kolja")
    assert state.display_name == "Kolja"
    mock_mark.assert_called_once()


@patch("arasul_tui.core.onboarding.mark_onboarded")
def test_save_name_skip(mock_mark):
    result = _save_name(_state(), "skip")
    assert result.ok is True
    assert result.refresh is True
    mock_mark.assert_called_once()


@patch("arasul_tui.core.onboarding.mark_onboarded")
def test_save_name_empty(mock_mark):
    result = _save_name(_state(), "")
    assert result.ok is True
    mock_mark.assert_called_once()
