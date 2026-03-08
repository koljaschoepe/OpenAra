from __future__ import annotations

from unittest.mock import patch

from arasul_tui.commands.tailscale_cmd import cmd_tailscale
from arasul_tui.core.router import REGISTRY
from arasul_tui.core.state import TuiState


def _state() -> TuiState:
    return TuiState(registry=REGISTRY)


def test_tailscale_default_shows_status():
    with patch("arasul_tui.commands.tailscale_cmd._is_installed", return_value=False):
        result = cmd_tailscale(_state(), [])
    assert result.ok is True


def test_tailscale_status_subcommand():
    with patch("arasul_tui.commands.tailscale_cmd._is_installed", return_value=False):
        result = cmd_tailscale(_state(), ["status"])
    assert result.ok is True


def test_tailscale_unknown_subcommand():
    result = cmd_tailscale(_state(), ["bogus"])
    assert result.ok is False


def test_tailscale_install_already_installed():
    with (
        patch("arasul_tui.commands.tailscale_cmd._is_installed", return_value=True),
        patch("arasul_tui.commands.tailscale_cmd.run_cmd", return_value="1.60.0"),
    ):
        result = cmd_tailscale(_state(), ["install"])
    assert result.ok is True


def test_tailscale_up_not_installed():
    with patch("arasul_tui.commands.tailscale_cmd._is_installed", return_value=False):
        result = cmd_tailscale(_state(), ["up"])
    assert result.ok is False


def test_tailscale_up_already_connected():
    with (
        patch("arasul_tui.commands.tailscale_cmd._is_installed", return_value=True),
        patch("arasul_tui.commands.tailscale_cmd._is_connected", return_value=True),
        patch("arasul_tui.commands.tailscale_cmd.run_cmd", return_value="100.64.0.1"),
    ):
        result = cmd_tailscale(_state(), ["up"])
    assert result.ok is True


def test_tailscale_down_not_installed():
    with patch("arasul_tui.commands.tailscale_cmd._is_installed", return_value=False):
        result = cmd_tailscale(_state(), ["down"])
    assert result.ok is False


def test_tailscale_down_not_connected():
    with (
        patch("arasul_tui.commands.tailscale_cmd._is_installed", return_value=True),
        patch("arasul_tui.commands.tailscale_cmd._is_connected", return_value=False),
    ):
        result = cmd_tailscale(_state(), ["down"])
    assert result.ok is True


def test_tailscale_down_success():
    with (
        patch("arasul_tui.commands.tailscale_cmd._is_installed", return_value=True),
        patch("arasul_tui.commands.tailscale_cmd._is_connected", return_value=True),
        patch("arasul_tui.commands.tailscale_cmd.run_cmd", return_value=""),
    ):
        result = cmd_tailscale(_state(), ["down"])
    assert result.ok is True
