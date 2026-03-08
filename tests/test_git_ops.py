from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from arasul_tui.commands.git_ops import cmd_git
from arasul_tui.core.router import REGISTRY
from arasul_tui.core.state import TuiState


def _state(tmp_path: Path | None = None) -> TuiState:
    s = TuiState(registry=REGISTRY)
    if tmp_path:
        s.active_project = tmp_path
    return s


def test_git_no_args_logged_in():
    with patch("arasul_tui.commands.git_ops.run_cmd", return_value="Logged in"):
        result = cmd_git(_state(), [])
    assert result.ok is True


def test_git_no_args_not_logged_in():
    with (
        patch("arasul_tui.commands.git_ops.run_cmd", return_value="not logged in"),
        patch("arasul_tui.commands.git_ops._git_install_gh", return_value=(True, "gh version 2.0")),
        patch("arasul_tui.commands.git_ops._git_setup_known_hosts"),
    ):
        result = cmd_git(_state(), [])
    # Wizard starts — returns prompt for token
    assert result.ok is True


def test_git_pull_no_project():
    result = cmd_git(_state(), ["pull"])
    assert result.ok is False


def test_git_push_no_project():
    result = cmd_git(_state(), ["push"])
    assert result.ok is False


def test_git_log_no_project():
    result = cmd_git(_state(), ["log"])
    assert result.ok is False


def test_git_status_no_project():
    result = cmd_git(_state(), ["status"])
    assert result.ok is False


def test_git_pull_up_to_date(tmp_path: Path):
    with patch("arasul_tui.commands.git_ops.run_cmd", return_value="Already up to date."):
        result = cmd_git(_state(tmp_path), ["pull"])
    assert result.ok is True


def test_git_pull_error(tmp_path: Path):
    with patch("arasul_tui.commands.git_ops.run_cmd", return_value="fatal: not a git repository"):
        result = cmd_git(_state(tmp_path), ["pull"])
    assert result.ok is False


def test_git_push_success(tmp_path: Path):
    with patch("arasul_tui.commands.git_ops.run_cmd", return_value="Everything up-to-date"):
        result = cmd_git(_state(tmp_path), ["push"])
    assert result.ok is True


def test_git_log_with_history(tmp_path: Path):
    log_output = "abc1234 First commit\ndef5678 Second commit"
    with patch("arasul_tui.commands.git_ops.run_cmd", return_value=log_output):
        result = cmd_git(_state(tmp_path), ["log"])
    assert result.ok is True


def test_git_log_empty(tmp_path: Path):
    with patch("arasul_tui.commands.git_ops.run_cmd", return_value=""):
        result = cmd_git(_state(tmp_path), ["log"])
    assert result.ok is True


def test_git_status_clean(tmp_path: Path):
    with patch("arasul_tui.commands.git_ops.run_cmd", return_value=""):
        result = cmd_git(_state(tmp_path), ["status"])
    assert result.ok is True


def test_git_status_dirty(tmp_path: Path):
    with patch("arasul_tui.commands.git_ops.run_cmd", return_value="M file.py"):
        result = cmd_git(_state(tmp_path), ["status"])
    assert result.ok is True


def test_git_unknown_subcommand(tmp_path: Path):
    result = cmd_git(_state(tmp_path), ["bogus"])
    assert result.ok is False
