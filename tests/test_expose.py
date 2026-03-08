"""Tests for /expose command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from arasul_tui.commands.expose_cmd import cmd_expose
from arasul_tui.core.state import TuiState


@pytest.fixture
def state(tmp_path: Path) -> TuiState:
    s = TuiState()
    s.project_root = tmp_path
    s.active_project = tmp_path / "my-app"
    return s


def test_expose_no_project():
    state = TuiState()
    state.active_project = None
    result = cmd_expose(state, [])
    assert result.ok is False


@patch("arasul_tui.commands.expose_cmd._is_tailscale_running", return_value=False)
def test_expose_status_no_tailscale(mock_ts, state: TuiState):
    result = cmd_expose(state, ["status"])
    assert result.ok is False


@patch("arasul_tui.commands.expose_cmd._is_tailscale_running", return_value=True)
@patch("arasul_tui.commands.expose_cmd._get_funnel_status", return_value=[])
def test_expose_status_no_routes(mock_funnel, mock_ts, state: TuiState):
    result = cmd_expose(state, ["status"])
    assert result.ok is True


@patch("arasul_tui.commands.expose_cmd._is_tailscale_running", return_value=True)
@patch("arasul_tui.commands.expose_cmd._get_funnel_status", return_value=[("Route", "https://example.ts.net:443")])
def test_expose_status_with_routes(mock_funnel, mock_ts, state: TuiState):
    result = cmd_expose(state, ["status"])
    assert result.ok is True


@patch("arasul_tui.commands.expose_cmd._is_tailscale_running", return_value=False)
def test_expose_on_no_tailscale(mock_ts, state: TuiState):
    result = cmd_expose(state, ["on"])
    assert result.ok is False


def test_expose_invalid_subcommand(state: TuiState):
    result = cmd_expose(state, ["invalid"])
    assert result.ok is False


def test_expose_defaults_to_status(state: TuiState):
    """No subcommand defaults to status."""
    with (
        patch("arasul_tui.commands.expose_cmd._is_tailscale_running", return_value=True),
        patch("arasul_tui.commands.expose_cmd._get_funnel_status", return_value=[]),
    ):
        result = cmd_expose(state, [])
    assert result.ok is True
