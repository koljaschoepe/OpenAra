"""Tests for command routing and dispatch (core/router.py).

Strategy: Tests verify the dispatch loop: parsing → registry lookup →
handler execution → result. Individual command behavior is tested in
their own files. This file focuses on routing mechanics.
"""

from __future__ import annotations

from arasul_tui.core.router import REGISTRY, run_command
from arasul_tui.core.state import TuiState


def test_empty_input(state: TuiState):
    """Empty input returns ok=True with silent style (no-op)."""
    result = run_command(state, "")
    assert result.ok is True
    assert result.style == "silent"


def test_empty_after_strip(state: TuiState):
    """Whitespace-only input treated as empty."""
    result = run_command(state, "   ")
    assert result.ok is True


def test_unknown_command_no_slash(state: TuiState):
    """Unrecognized natural language input returns ok=False."""
    result = run_command(state, "foobar")
    assert result.ok is False


def test_unknown_slash_command(state: TuiState):
    """Unrecognized slash command returns ok=False."""
    result = run_command(state, "/nonexistent")
    assert result.ok is False


def test_help_command(state: TuiState):
    """/help is routed correctly and returns silent result."""
    result = run_command(state, "/help")
    assert result.ok is True
    assert result.style == "silent"


def test_exit_command(state: TuiState):
    """/exit sets quit_app flag."""
    result = run_command(state, "/exit")
    assert result.ok is True
    assert result.quit_app is True


def test_registry_command_count():
    """Registry has exactly 24 commands."""
    assert len(REGISTRY.names()) == 24


def test_slash_only(state: TuiState):
    """Bare '/' treated as empty input."""
    result = run_command(state, "/")
    assert result.ok is True
    assert result.style == "silent"


def test_parse_error_unmatched_quote(state: TuiState):
    """Unmatched quote in input returns ok=False."""
    result = run_command(state, '/open "unclosed')
    assert result.ok is False


def test_prefix_auto_execute(state: TuiState):
    """Unique prefix in slash mode auto-executes (e.g. /hel → /help)."""
    result = run_command(state, "/hel")
    assert result.ok is True
    assert result.style == "silent"


def test_registry_categories():
    """Registry organizes commands into expected categories."""
    cats = REGISTRY.categories()
    assert "Projects" in cats
    assert "Claude Code" in cats
    assert "System" in cats
    assert "Security" in cats
    assert "Services" in cats
    assert "Meta" in cats
