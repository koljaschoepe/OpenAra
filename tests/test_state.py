from __future__ import annotations

from pathlib import Path

from arasul_tui.core.state import Screen, TuiState, default_project_root


def test_default_state():
    state = TuiState()
    assert state.active_project is None
    assert state.project_root == default_project_root()
    assert state.first_run is True
    assert state.screen == Screen.MAIN


def test_state_custom_root(tmp_path: Path):
    state = TuiState(project_root=tmp_path)
    assert state.project_root == tmp_path


def test_state_active_project(tmp_path: Path):
    state = TuiState()
    project = tmp_path / "my-project"
    project.mkdir()
    state.active_project = project
    assert state.active_project == project
    assert state.active_project.name == "my-project"


def test_state_wizard_fields():
    state = TuiState()
    assert state._wizard_token is None
    assert state._wizard_uuid is None
    assert state._delete_target is None

    state._wizard_token = "test-token"
    assert state._wizard_token == "test-token"


def test_state_wizard_dict():
    state = TuiState()
    assert state._wizard == {}

    state._wizard["custom_key"] = "custom_value"
    assert state._wizard["custom_key"] == "custom_value"

    # Legacy properties delegate to _wizard
    state._wizard_token = "tk"
    assert state._wizard["token"] == "tk"


def test_state_screen_enum():
    state = TuiState()
    assert state.screen == Screen.MAIN
    state.screen = Screen.PROJECT
    assert state.screen == Screen.PROJECT
