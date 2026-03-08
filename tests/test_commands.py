from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from arasul_tui.commands import (
    _clone_finish,
    _create_finish,
    _delete_confirm,
    _delete_select,
    cmd_create,
    cmd_delete,
    cmd_open,
)
from arasul_tui.commands.project import cmd_info, cmd_repos
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
    assert result.ok is False


# ---------------------------------------------------------------------------
# /info tests (10.5)
# ---------------------------------------------------------------------------


def test_info_no_project(state: TuiState):
    result = cmd_info(state, [])
    assert result.ok is False


def test_info_nonexistent_arg(state_with_projects: TuiState):
    result = cmd_info(state_with_projects, ["nonexistent"])
    assert result.ok is False


def test_info_by_name(state_with_projects: TuiState):
    with (
        patch("arasul_tui.core.git_info.get_git_info", return_value=None),
        patch("arasul_tui.core.git_info.get_readme_headline", return_value=None),
        patch("arasul_tui.core.git_info.detect_language", return_value="Python"),
        patch("arasul_tui.core.git_info.get_disk_usage", return_value="42M"),
        patch("arasul_tui.core.n8n_project.is_n8n_project_name", return_value=False),
    ):
        result = cmd_info(state_with_projects, ["alpha"])
    assert result.ok is True


def test_info_active_project(state_with_projects: TuiState):
    state_with_projects.active_project = state_with_projects.project_root / "beta"
    with (
        patch("arasul_tui.core.git_info.get_git_info", return_value=None),
        patch("arasul_tui.core.git_info.get_readme_headline", return_value="A cool project"),
        patch("arasul_tui.core.git_info.detect_language", return_value=None),
        patch("arasul_tui.core.git_info.get_disk_usage", return_value=None),
        patch("arasul_tui.core.n8n_project.is_n8n_project_name", return_value=False),
    ):
        result = cmd_info(state_with_projects, [])
    assert result.ok is True


def test_info_with_git(state_with_projects: TuiState):
    from arasul_tui.core.git_info import GitInfo

    git = GitInfo(
        branch="main",
        is_dirty=True,
        short_hash="abc1234",
        commit_message="fix bug",
        commit_time="2h ago",
        remote_url="https://github.com/user/repo",
    )
    state_with_projects.active_project = state_with_projects.project_root / "alpha"
    with (
        patch("arasul_tui.core.git_info.get_git_info", return_value=git),
        patch("arasul_tui.core.git_info.get_readme_headline", return_value=None),
        patch("arasul_tui.core.git_info.detect_language", return_value=None),
        patch("arasul_tui.core.git_info.get_disk_usage", return_value=None),
        patch("arasul_tui.core.n8n_project.is_n8n_project_name", return_value=False),
    ):
        result = cmd_info(state_with_projects, [])
    assert result.ok is True


# ---------------------------------------------------------------------------
# /repos tests (10.5)
# ---------------------------------------------------------------------------


def test_repos_no_projects(state: TuiState):
    result = cmd_repos(state, [])
    assert result.ok is False


def test_repos_with_projects(state_with_projects: TuiState):
    with patch("arasul_tui.core.git_info.get_git_info", return_value=None):
        result = cmd_repos(state_with_projects, [])
    assert result.ok is True


def test_repos_with_active_project(state_with_projects: TuiState):
    from arasul_tui.core.git_info import GitInfo

    git = GitInfo(branch="main", is_dirty=False, commit_time="1d ago")
    state_with_projects.active_project = state_with_projects.project_root / "alpha"
    with patch("arasul_tui.core.git_info.get_git_info", return_value=git):
        result = cmd_repos(state_with_projects, [])
    assert result.ok is True
