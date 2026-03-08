from __future__ import annotations

from arasul_tui.core.router import REGISTRY, run_command
from arasul_tui.core.state import TuiState


def test_empty_input(state: TuiState):
    result = run_command(state, "")
    assert result.ok is True
    assert result.style == "silent"


def test_empty_after_strip(state: TuiState):
    result = run_command(state, "   ")
    assert result.ok is True


def test_unknown_command_no_slash(state: TuiState):
    result = run_command(state, "foobar")
    assert result.ok is False


def test_unknown_slash_command(state: TuiState):
    result = run_command(state, "/nonexistent")
    assert result.ok is False


def test_help_command(state: TuiState):
    result = run_command(state, "/help")
    assert result.ok is True
    assert result.style == "silent"


def test_exit_command(state: TuiState):
    result = run_command(state, "/exit")
    assert result.ok is True
    assert result.quit_app is True


def test_registry_has_all_commands():
    expected = {
        "help",
        "open",
        "create",
        "clone",
        "status",
        "claude",
        "git",
        "browser",
        "delete",
        "exit",
        "info",
        "repos",
        "auth",
        "health",
        "setup",
        "docker",
        "keys",
        "logins",
        "security",
        "mcp",
        "expose",
        "n8n",
        "tailscale",
        "welcome",
    }
    actual = set(REGISTRY.names())
    assert expected == actual


def test_registry_command_count():
    assert len(REGISTRY.names()) == 24


def test_slash_only(state: TuiState):
    result = run_command(state, "/")
    assert result.ok is True
    assert result.style == "silent"


def test_parse_error_unmatched_quote(state: TuiState):
    result = run_command(state, '/open "unclosed')
    assert result.ok is False


def test_prefix_auto_execute(state: TuiState):
    """Unique prefix in slash mode auto-executes the matching command."""
    result = run_command(state, "/hel")
    assert result.ok is True
    assert result.style == "silent"  # help returns silent


def test_registry_categories():
    cats = REGISTRY.categories()
    assert "Projects" in cats
    assert "Claude Code" in cats
    assert "System" in cats
    assert "Security" in cats
    assert "Services" in cats
    assert "Meta" in cats
