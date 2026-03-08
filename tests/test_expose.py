"""Tests for /expose command."""

from __future__ import annotations

import subprocess
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


def test_expose_status_no_project():
    """Status works even without an active project."""
    state = TuiState()
    state.active_project = None
    with (
        patch("arasul_tui.commands.expose_cmd._is_tailscale_running", return_value=True),
        patch("arasul_tui.commands.expose_cmd._get_funnel_status", return_value=[]),
    ):
        result = cmd_expose(state, [])
    assert result.ok is True


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


def test_expose_on_invalid_port(state: TuiState):
    """Port validation rejects non-numeric and out-of-range values."""
    result = cmd_expose(state, ["on", "abc"])
    assert result.ok is False

    result = cmd_expose(state, ["on", "0"])
    assert result.ok is False

    result = cmd_expose(state, ["on", "99999"])
    assert result.ok is False


def test_expose_defaults_to_status(state: TuiState):
    """No subcommand defaults to status."""
    with (
        patch("arasul_tui.commands.expose_cmd._is_tailscale_running", return_value=True),
        patch("arasul_tui.commands.expose_cmd._get_funnel_status", return_value=[]),
    ):
        result = cmd_expose(state, [])
    assert result.ok is True


# ---------------------------------------------------------------------------
# on/off subcommand tests (10.3)
# ---------------------------------------------------------------------------


@patch("arasul_tui.commands.expose_cmd._is_tailscale_running", return_value=True)
@patch("arasul_tui.commands.expose_cmd.spinner_run")
def test_expose_on_success(mock_spinner, mock_ts, state: TuiState):
    mock_spinner.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="https://device.ts.net", stderr=""
    )
    result = cmd_expose(state, ["on"])
    assert result.ok is True
    mock_spinner.assert_called_once()


@patch("arasul_tui.commands.expose_cmd._is_tailscale_running", return_value=True)
@patch("arasul_tui.commands.expose_cmd.spinner_run")
def test_expose_on_custom_port(mock_spinner, mock_ts, state: TuiState):
    mock_spinner.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    result = cmd_expose(state, ["on", "8080"])
    assert result.ok is True


@patch("arasul_tui.commands.expose_cmd._is_tailscale_running", return_value=True)
@patch("arasul_tui.commands.expose_cmd.spinner_run")
def test_expose_on_failure(mock_spinner, mock_ts, state: TuiState):
    mock_spinner.return_value = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="permission denied"
    )
    result = cmd_expose(state, ["on"])
    assert result.ok is False


@patch("arasul_tui.commands.expose_cmd._is_tailscale_running", return_value=True)
@patch("arasul_tui.commands.expose_cmd.spinner_run")
def test_expose_on_timeout(mock_spinner, mock_ts, state: TuiState):
    mock_spinner.side_effect = subprocess.TimeoutExpired(cmd="tailscale", timeout=30)
    result = cmd_expose(state, ["on"])
    assert result.ok is False


@patch("arasul_tui.commands.expose_cmd.spinner_run")
def test_expose_off_success(mock_spinner, state: TuiState):
    mock_spinner.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    result = cmd_expose(state, ["off"])
    assert result.ok is True


@patch("arasul_tui.commands.expose_cmd.spinner_run")
def test_expose_off_failure(mock_spinner, state: TuiState):
    mock_spinner.return_value = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="error")
    result = cmd_expose(state, ["off"])
    assert result.ok is False


@patch("arasul_tui.commands.expose_cmd.spinner_run")
def test_expose_off_os_error(mock_spinner, state: TuiState):
    mock_spinner.side_effect = OSError("tailscale not found")
    result = cmd_expose(state, ["off"])
    assert result.ok is False
