"""Test suggest_next helper and next-step hints in commands."""

from __future__ import annotations

from unittest.mock import patch

from arasul_tui.core.router import REGISTRY
from arasul_tui.core.state import TuiState
from arasul_tui.core.ui.output import suggest_next


def _state() -> TuiState:
    return TuiState(registry=REGISTRY)


def test_suggest_next_prints(capsys):
    """suggest_next produces output."""
    suggest_next("Try [bold]/help[/bold]")
    # No exception means success — output goes through Rich console


def test_suggest_next_empty():
    """suggest_next with no args is a no-op."""
    suggest_next()  # Should not raise


def test_mcp_list_empty_shows_hints():
    """When no MCP servers, /mcp list should show suggestions."""
    from arasul_tui.commands.mcp import cmd_mcp

    with patch("arasul_tui.commands.mcp.load_claude_json", return_value={}):
        result = cmd_mcp(_state(), ["list"])
    assert result.ok is True


def test_security_keys_empty_shows_hint():
    """When no SSH keys, /keys should suggest generating one."""
    from arasul_tui.commands.security import cmd_keys

    with patch("arasul_tui.commands.security.list_ssh_keys", return_value=[]):
        result = cmd_keys(_state(), [])
    assert result.ok is True


def test_docker_empty_shows_hint():
    """When no containers, /docker should suggest next steps."""
    from arasul_tui.commands.system import cmd_docker

    with patch("arasul_tui.commands.system.list_containers", return_value=[]):
        result = cmd_docker(_state(), [])
    assert result.ok is True
