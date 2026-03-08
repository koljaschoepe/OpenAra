from __future__ import annotations

from arasul_tui.commands.meta import cmd_help
from arasul_tui.core.state import Screen, TuiState


def test_help_returns_ok(state: TuiState):
    result = cmd_help(state, [])
    assert result.ok is True
    assert result.style == "silent"


def test_help_main_screen(state: TuiState):
    state.screen = Screen.MAIN
    state.active_project = None
    result = cmd_help(state, [])
    assert result.ok is True


def test_help_project_screen(state_with_projects: TuiState):
    state_with_projects.active_project = state_with_projects.project_root / "alpha"
    state_with_projects.screen = Screen.PROJECT
    result = cmd_help(state_with_projects, [])
    assert result.ok is True


def test_help_specific_command(state: TuiState):
    result = cmd_help(state, ["status"])
    assert result.ok is True


def test_help_specific_command_alias(state: TuiState):
    result = cmd_help(state, ["new"])
    assert result.ok is True


def test_help_unknown_command(state: TuiState):
    result = cmd_help(state, ["nonexistent"])
    assert result.ok is True  # still returns ok, just prints "not found"


def test_help_via_slash(state: TuiState):
    from arasul_tui.core.router import run_command

    result = run_command(state, "/help")
    assert result.ok is True


def test_help_with_arg_via_slash(state: TuiState):
    from arasul_tui.core.router import run_command

    result = run_command(state, "/help status")
    assert result.ok is True
