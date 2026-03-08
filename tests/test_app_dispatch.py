"""Tests for app.py dispatch logic, fuzzy matching, shortcuts, and completions."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from arasul_tui.app import (
    SmartCompleter,
    _dispatch_command,
    _fuzzy_match,
    _handle_number,
    _suggest_alternatives,
    _try_launch_shortcut,
)
from arasul_tui.core.router import REGISTRY
from arasul_tui.core.state import Screen, TuiState


@pytest.fixture
def state(tmp_path: Path) -> TuiState:
    s = TuiState(registry=REGISTRY)
    s.project_root = tmp_path
    return s


@pytest.fixture
def state_with_projects(state: TuiState) -> TuiState:
    for name in ("alpha", "beta", "gamma"):
        (state.project_root / name).mkdir()
    return state


# ---------------------------------------------------------------------------
# _fuzzy_match
# ---------------------------------------------------------------------------


class TestFuzzyMatch:
    def test_exact_match(self):
        assert _fuzzy_match("alpha", ["alpha", "beta"]) == ["alpha"]

    def test_prefix_match(self):
        assert _fuzzy_match("al", ["alpha", "beta"]) == ["alpha"]

    def test_substring_match(self):
        assert _fuzzy_match("ph", ["alpha", "beta"]) == ["alpha"]

    def test_no_match(self):
        assert _fuzzy_match("xyz", ["alpha", "beta"]) == []

    def test_multiple_prefix(self):
        result = _fuzzy_match("a", ["alpha", "api-server", "beta"])
        assert "alpha" in result
        assert "api-server" in result
        assert "beta" not in result

    def test_fuzzy_char_match(self):
        result = _fuzzy_match("ag", ["alpha-gamma", "beta"])
        assert len(result) >= 1
        assert "alpha-gamma" in result

    def test_case_insensitive(self):
        assert _fuzzy_match("Alpha", ["alpha"]) == ["alpha"]

    def test_empty_query(self):
        result = _fuzzy_match("", ["alpha", "beta"])
        # Empty matches all via prefix
        assert len(result) >= 2


# ---------------------------------------------------------------------------
# _handle_number
# ---------------------------------------------------------------------------


class TestHandleNumber:
    def test_valid_number(self, state_with_projects: TuiState):
        with patch("arasul_tui.app.project_list", return_value=["alpha", "beta", "gamma"]):
            result = _handle_number(state_with_projects, 1)
        assert result is True
        assert state_with_projects.active_project is not None
        assert state_with_projects.active_project.name == "alpha"

    def test_number_too_high(self, state_with_projects: TuiState):
        with patch("arasul_tui.app.project_list", return_value=["alpha"]):
            result = _handle_number(state_with_projects, 5)
        assert result is False

    def test_zero(self, state_with_projects: TuiState):
        with patch("arasul_tui.app.project_list", return_value=["alpha"]):
            result = _handle_number(state_with_projects, 0)
        assert result is False

    def test_negative(self, state_with_projects: TuiState):
        with patch("arasul_tui.app.project_list", return_value=["alpha"]):
            result = _handle_number(state_with_projects, -1)
        assert result is False

    def test_nonexistent_dir(self, state: TuiState):
        with patch("arasul_tui.app.project_list", return_value=["ghost"]):
            result = _handle_number(state, 1)
        assert result is False


# ---------------------------------------------------------------------------
# _try_launch_shortcut
# ---------------------------------------------------------------------------


class TestTryLaunchShortcut:
    def test_no_active_project(self, state: TuiState):
        state.active_project = None
        assert _try_launch_shortcut(state, "g") is None

    def test_lazygit_found(self, state: TuiState):
        state.active_project = Path("/tmp/proj")
        with patch("shutil.which", return_value="/usr/bin/lazygit"):
            result = _try_launch_shortcut(state, "g")
        assert result == ("lazygit", Path("/tmp/proj"))

    def test_lazygit_full_name(self, state: TuiState):
        state.active_project = Path("/tmp/proj")
        with patch("shutil.which", return_value="/usr/bin/lazygit"):
            result = _try_launch_shortcut(state, "lazygit")
        assert result is not None

    def test_lazygit_not_installed(self, state: TuiState):
        state.active_project = Path("/tmp/proj")
        with patch("shutil.which", return_value=None):
            result = _try_launch_shortcut(state, "g")
        assert result is None

    def test_claude_configured(self, state: TuiState):
        state.active_project = Path("/tmp/proj")
        with (
            patch("arasul_tui.app.is_claude_configured", return_value=True),
            patch("shutil.which", return_value="/usr/bin/claude"),
        ):
            result = _try_launch_shortcut(state, "c")
        assert result == ("claude", Path("/tmp/proj"))

    def test_claude_not_configured(self, state: TuiState):
        state.active_project = Path("/tmp/proj")
        with patch("arasul_tui.app.is_claude_configured", return_value=False):
            result = _try_launch_shortcut(state, "c")
        assert result is None

    def test_claude_not_installed(self, state: TuiState):
        state.active_project = Path("/tmp/proj")
        with (
            patch("arasul_tui.app.is_claude_configured", return_value=True),
            patch("shutil.which", return_value=None),
        ):
            result = _try_launch_shortcut(state, "c")
        assert result is None

    def test_unknown_shortcut(self, state: TuiState):
        state.active_project = Path("/tmp/proj")
        assert _try_launch_shortcut(state, "x") is None


# ---------------------------------------------------------------------------
# _suggest_alternatives
# ---------------------------------------------------------------------------


class TestSuggestAlternatives:
    def test_close_match(self):
        """Should not crash and should suggest something for partial match."""
        _suggest_alternatives("statu")  # close to "status"

    def test_no_match(self):
        """Should not crash for completely unknown commands."""
        _suggest_alternatives("xyzqwerty")

    def test_alias_match(self):
        """Should check aliases too."""
        _suggest_alternatives("system")  # "system status" is an alias pattern


# ---------------------------------------------------------------------------
# _dispatch_command
# ---------------------------------------------------------------------------


class TestDispatchCommand:
    def test_shortcut_n_creates(self, state: TuiState):
        with patch("arasul_tui.app.run_command") as mock_run:
            mock_run.return_value = MagicMock(quit_app=False)
            result, launch, should_break = _dispatch_command(state, "n")
        mock_run.assert_called_once_with(state, "/create")

    def test_shortcut_d_deletes(self, state: TuiState):
        with patch("arasul_tui.app.run_command") as mock_run:
            mock_run.return_value = MagicMock(quit_app=False)
            result, launch, should_break = _dispatch_command(state, "d")
        mock_run.assert_called_once_with(state, "/delete")

    def test_number_selection(self, state_with_projects: TuiState):
        with patch("arasul_tui.app.project_list", return_value=["alpha", "beta", "gamma"]):
            result, launch, should_break = _dispatch_command(state_with_projects, "1")
        assert launch is None
        assert should_break is False

    def test_back_from_project(self, state: TuiState):
        state.active_project = Path("/tmp/proj")
        state.screen = Screen.PROJECT
        result, launch, should_break = _dispatch_command(state, "b")
        assert state.active_project is None
        assert state.screen == Screen.MAIN

    def test_back_already_main(self, state: TuiState):
        state.active_project = None
        result, launch, should_break = _dispatch_command(state, "back")
        assert result is None  # Just prints info

    def test_slash_command(self, state: TuiState):
        with patch("arasul_tui.app.run_command") as mock_run:
            mock_run.return_value = MagicMock(quit_app=False)
            result, launch, should_break = _dispatch_command(state, "/help")
        assert result is not None

    def test_unknown_command(self, state: TuiState):
        with patch("arasul_tui.app.project_list", return_value=[]):
            result, launch, should_break = _dispatch_command(state, "xyzqwerty")
        assert result is None
        assert should_break is False

    def test_c_without_claude_configured(self, state: TuiState):
        state.active_project = Path("/tmp/proj")
        with (
            patch("arasul_tui.app.is_claude_configured", return_value=False),
            patch("arasul_tui.app.run_command") as mock_run,
        ):
            mock_run.return_value = MagicMock(quit_app=False)
            _dispatch_command(state, "c")
        mock_run.assert_called_once_with(state, "/claude")


# ---------------------------------------------------------------------------
# SmartCompleter
# ---------------------------------------------------------------------------


class TestSmartCompleter:
    def _complete(self, text: str) -> list[str]:
        completer = SmartCompleter()
        doc = MagicMock()
        doc.text_before_cursor = text
        event = MagicMock()
        return [c.text for c in completer.get_completions(doc, event)]

    def test_empty_input(self):
        results = self._complete("")
        assert len(results) > 0  # Should list all commands

    def test_slash_prefix(self):
        results = self._complete("/he")
        assert any("help" in r for r in results)

    def test_slash_with_subcommand(self):
        results = self._complete("/git ")
        assert len(results) > 0  # Should show git subcommands

    def test_natural_language(self):
        results = self._complete("sta")
        assert any("status" in r for r in results)
