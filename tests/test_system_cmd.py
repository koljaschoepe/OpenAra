from __future__ import annotations

from unittest.mock import patch

from arasul_tui.commands.system import cmd_docker, cmd_health, cmd_status
from arasul_tui.core.router import REGISTRY
from arasul_tui.core.state import TuiState


def _state() -> TuiState:
    return TuiState(registry=REGISTRY)


def test_cmd_status():
    with patch("arasul_tui.commands.system.run_cmd", return_value=""):
        result = cmd_status(_state(), [])
    assert result.ok is True


def test_cmd_health():
    with patch("arasul_tui.commands.system.run_cmd", return_value=""):
        result = cmd_health(_state(), [])
    assert result.ok is True


def test_cmd_docker_not_installed():
    with patch("arasul_tui.commands.system.run_cmd", return_value=""):
        result = cmd_docker(_state(), [])
    assert result.ok is True
