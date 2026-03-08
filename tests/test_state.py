"""Tests for TUI state management (Screen, TuiState, wizard dict).

Strategy: Tests verify state initialization, project assignment, and
screen transitions. Wizard state chaining is tested at E2E level
in test_e2e_flow.py.
"""

from __future__ import annotations

from pathlib import Path

from arasul_tui.core.state import Screen, TuiState, default_project_root


def test_default_state():
    """Fresh state has expected defaults."""
    state = TuiState()
    assert state.active_project is None
    assert state.project_root == default_project_root()
    assert state.first_run is True
    assert state.screen == Screen.MAIN


def test_state_custom_root(tmp_path: Path):
    """Project root can be overridden."""
    state = TuiState(project_root=tmp_path)
    assert state.project_root == tmp_path


def test_state_active_project(tmp_path: Path):
    """Setting active_project provides name access."""
    state = TuiState()
    project = tmp_path / "my-project"
    project.mkdir()
    state.active_project = project
    assert state.active_project == project
    assert state.active_project.name == "my-project"


def test_state_screen_transition():
    """Screen can switch between MAIN and PROJECT."""
    state = TuiState()
    assert state.screen == Screen.MAIN
    state.screen = Screen.PROJECT
    assert state.screen == Screen.PROJECT
