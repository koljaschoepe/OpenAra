"""Tests for /help command across screen contexts.

Strategy: Tests verify help renders correctly in different states
(main screen, project screen, with arguments). Routing tests
(slash dispatch) live in test_router.py.
"""

from __future__ import annotations

from arasul_tui.commands.meta import cmd_help
from arasul_tui.core.state import Screen, TuiState


def test_help_returns_ok(state: TuiState):
    """Help command succeeds with silent style."""
    result = cmd_help(state, [])
    assert result.ok is True
    assert result.style == "silent"


def test_help_project_screen(state_with_projects: TuiState):
    """Help works in project context (different output than main)."""
    state_with_projects.active_project = state_with_projects.project_root / "alpha"
    state_with_projects.screen = Screen.PROJECT
    result = cmd_help(state_with_projects, [])
    assert result.ok is True


def test_help_specific_command(state: TuiState):
    """Help with a command name shows details for that command."""
    result = cmd_help(state, ["status"])
    assert result.ok is True


def test_help_specific_command_alias(state: TuiState):
    """Help resolves aliases (e.g. 'new' → 'create')."""
    result = cmd_help(state, ["new"])
    assert result.ok is True


def test_help_unknown_command(state: TuiState):
    """Help with unknown command still returns ok (prints 'not found')."""
    result = cmd_help(state, ["nonexistent"])
    assert result.ok is True
