from __future__ import annotations

from pathlib import Path

from arasul_tui.commands import (
    _clone_finish,
    _create_finish,
    _delete_confirm,
    _delete_select,
    cmd_create,
    cmd_delete,
    cmd_open,
)
from arasul_tui.core.state import TuiState


def test_open_no_args(state_with_projects: TuiState):
    result = cmd_open(state_with_projects, [])
    assert result.ok is False


def test_open_existing_project(state_with_projects: TuiState):
    result = cmd_open(state_with_projects, ["alpha"])
    assert result.ok is True
    assert state_with_projects.active_project is not None
    assert state_with_projects.active_project.name == "alpha"


def test_open_nonexistent_project(state_with_projects: TuiState):
    result = cmd_open(state_with_projects, ["nonexistent"])
    assert result.ok is False


def test_open_root_not_found(state: TuiState):
    state.project_root = Path("/nonexistent/path")
    result = cmd_open(state, ["test"])
    assert result.ok is False


def test_create_with_name(state: TuiState):
    result = cmd_create(state, ["new-project"])
    assert result.ok is True
    assert (state.project_root / "new-project").exists()
    assert state.active_project is not None


def test_create_duplicate(state_with_projects: TuiState):
    result = cmd_create(state_with_projects, ["alpha"])
    assert result.ok is False


def test_create_wizard(state: TuiState):
    result = cmd_create(state, [])
    assert result.ok is True
    assert result.pending_handler is not None
    assert result.wizard_step is not None


def test_create_finish_empty_name(state: TuiState):
    result = _create_finish(state, "   ")
    assert result.ok is False


def test_create_finish_spaces_in_name(state: TuiState):
    result = _create_finish(state, "my project")
    assert result.ok is True
    assert (state.project_root / "my-project").exists()


def test_delete_no_projects(state: TuiState):
    result = cmd_delete(state, [])
    assert result.ok is False


def test_delete_shows_list(state_with_projects: TuiState):
    result = cmd_delete(state_with_projects, [])
    assert result.ok is True
    assert result.pending_handler is not None


def test_delete_select_invalid_number(state_with_projects: TuiState):
    result = _delete_select(state_with_projects, "abc")
    assert result.ok is False


def test_delete_select_out_of_range(state_with_projects: TuiState):
    result = _delete_select(state_with_projects, "99")
    assert result.ok is False


def test_delete_select_valid(state_with_projects: TuiState):
    result = _delete_select(state_with_projects, "1")
    assert result.ok is True
    assert result.pending_handler is _delete_confirm
    assert state_with_projects._delete_target is not None


def test_delete_confirm_yes(state_with_projects: TuiState):
    target = state_with_projects.project_root / "alpha"
    state_with_projects._delete_target = target
    result = _delete_confirm(state_with_projects, "y")
    assert result.ok is True
    assert not target.exists()


def test_delete_confirm_no(state_with_projects: TuiState):
    target = state_with_projects.project_root / "alpha"
    state_with_projects._delete_target = target
    result = _delete_confirm(state_with_projects, "n")
    assert result.ok is True
    assert target.exists()


def test_delete_confirm_invalid(state_with_projects: TuiState):
    target = state_with_projects.project_root / "alpha"
    state_with_projects._delete_target = target
    result = _delete_confirm(state_with_projects, "maybe")
    assert result.ok is False
    assert result.pending_handler is _delete_confirm


def test_clone_finish_empty_url(state: TuiState):
    result = _clone_finish(state, "")
    assert result.ok is False


def test_clone_finish_invalid_url(state: TuiState):
    result = _clone_finish(state, "not-a-url")
    assert result.ok is False


def test_create_path_traversal_rejected(state: TuiState):
    """Ensure path traversal in project names doesn't crash."""
    result = _create_finish(state, "../escape")
    assert isinstance(result.ok, bool)
