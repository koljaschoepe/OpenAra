"""Tests for /git command handler and subcommands.

Strategy: Subcommands that require an active project are tested both
without (parametrized rejection) and with a project (individual behavior).
The auth wizard is tested in test_e2e_flow.py at the E2E level.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from arasul_tui.commands.git_ops import cmd_git
from arasul_tui.core.state import TuiState


def _state_with_project(tmp_path: Path) -> TuiState:
    """Create a TuiState with an active project that has a .git directory."""
    from arasul_tui.core.router import REGISTRY

    s = TuiState(registry=REGISTRY)
    s.active_project = tmp_path
    (tmp_path / ".git").mkdir(exist_ok=True)
    return s


def test_git_no_args_logged_in():
    """No args + already logged in shows git status."""
    from arasul_tui.core.router import REGISTRY

    with patch("arasul_tui.commands.git_ops.run_cmd", return_value="Logged in"):
        result = cmd_git(TuiState(registry=REGISTRY), [])
    assert result.ok is True


def test_git_no_args_not_logged_in():
    """No args + not logged in starts the auth wizard."""
    from arasul_tui.core.router import REGISTRY

    with (
        patch("arasul_tui.commands.git_ops.run_cmd", return_value="not logged in"),
        patch("arasul_tui.commands.git_ops._git_install_gh", return_value=(True, "gh version 2.0")),
        patch("arasul_tui.commands.git_ops._git_setup_known_hosts"),
    ):
        result = cmd_git(TuiState(registry=REGISTRY), [])
    assert result.ok is True


@pytest.mark.parametrize("subcmd", ["pull", "push", "log", "status"])
def test_git_subcommands_require_project(subcmd: str):
    """All git subcommands fail without an active project."""
    from arasul_tui.core.router import REGISTRY

    result = cmd_git(TuiState(registry=REGISTRY), [subcmd])
    assert result.ok is False


def test_git_pull_up_to_date(tmp_path: Path):
    """Successful pull returns ok=True."""
    with patch("arasul_tui.commands.git_ops.run_cmd", return_value="Already up to date."):
        result = cmd_git(_state_with_project(tmp_path), ["pull"])
    assert result.ok is True


def test_git_pull_error(tmp_path: Path):
    """Pull failure (not a git repo) returns ok=False."""
    with patch("arasul_tui.commands.git_ops.run_cmd", return_value="fatal: not a git repository"):
        result = cmd_git(_state_with_project(tmp_path), ["pull"])
    assert result.ok is False


def test_git_push_success(tmp_path: Path):
    """Successful push returns ok=True."""
    with patch("arasul_tui.commands.git_ops.run_cmd", return_value="Everything up-to-date"):
        result = cmd_git(_state_with_project(tmp_path), ["push"])
    assert result.ok is True


def test_git_log_with_history(tmp_path: Path):
    """Log with commits returns ok=True."""
    with patch("arasul_tui.commands.git_ops.run_cmd", return_value="abc1234 First commit\ndef5678 Second"):
        result = cmd_git(_state_with_project(tmp_path), ["log"])
    assert result.ok is True


def test_git_status_clean(tmp_path: Path):
    """Clean working tree returns ok=True."""
    with patch("arasul_tui.commands.git_ops.run_cmd", return_value=""):
        result = cmd_git(_state_with_project(tmp_path), ["status"])
    assert result.ok is True


def test_git_unknown_subcommand(tmp_path: Path):
    """Unknown subcommand returns ok=False."""
    result = cmd_git(_state_with_project(tmp_path), ["bogus"])
    assert result.ok is False
