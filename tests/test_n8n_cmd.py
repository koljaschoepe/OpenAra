from __future__ import annotations

from unittest.mock import patch

from arasul_tui.commands.n8n_cmd import cmd_n8n
from arasul_tui.core.state import TuiState


def test_n8n_not_installed_triggers_install(state: TuiState):
    """When not installed, smart flow tries to install (fails gracefully without sudo)."""
    with (
        patch("arasul_tui.commands.n8n_cmd.n8n_is_installed", return_value=False),
        patch("arasul_tui.commands.n8n_cmd.run_cmd", return_value=""),
    ):
        result = cmd_n8n(state, [])
    assert result.ok is False


def test_n8n_installed_stopped_starts(state: TuiState):
    """When installed but stopped, smart flow starts containers."""
    call_count = 0

    def _is_running():
        nonlocal call_count
        call_count += 1
        # First call: stopped, second call (after start): running
        return call_count > 1

    with (
        patch("arasul_tui.commands.n8n_cmd.n8n_is_installed", return_value=True),
        patch("arasul_tui.commands.n8n_cmd.n8n_is_running", side_effect=_is_running),
        patch("arasul_tui.commands.n8n_cmd.n8n_compose_cmd", return_value=""),
        patch("arasul_tui.commands.n8n_cmd.n8n_get_api_key", return_value="test-key-12345"),
        patch("arasul_tui.commands.n8n_cmd.is_n8n_mcp_configured", return_value=True),
        patch(
            "arasul_tui.commands.n8n_cmd.n8n_health",
            return_value={
                "container": "Up 5 min",
                "postgres": "Up 5 min",
                "api": "healthy",
            },
        ),
        patch("arasul_tui.commands.n8n_cmd.n8n_list_workflows", return_value=[]),
        patch("arasul_tui.commands.n8n_cmd._ensure_n8n_project"),
    ):
        result = cmd_n8n(state, [])
    assert result.ok is True


def test_n8n_running_no_api_key_prompts(state: TuiState):
    """When running but no API key, prompts for key."""
    with (
        patch("arasul_tui.commands.n8n_cmd.n8n_is_installed", return_value=True),
        patch("arasul_tui.commands.n8n_cmd.n8n_is_running", return_value=True),
        patch("arasul_tui.commands.n8n_cmd.n8n_get_api_key", return_value=None),
    ):
        result = cmd_n8n(state, [])
    assert result.ok is True
    assert result.pending_handler is not None
    assert result.prompt == "Paste API key"


def test_n8n_running_all_ok_shows_status(state: TuiState):
    """When everything is set up, shows status dashboard."""
    with (
        patch("arasul_tui.commands.n8n_cmd.n8n_is_installed", return_value=True),
        patch("arasul_tui.commands.n8n_cmd.n8n_is_running", return_value=True),
        patch("arasul_tui.commands.n8n_cmd.n8n_get_api_key", return_value="test-key-12345"),
        patch("arasul_tui.commands.n8n_cmd.is_n8n_mcp_configured", return_value=True),
        patch(
            "arasul_tui.commands.n8n_cmd.n8n_health",
            return_value={
                "container": "Up 5 min",
                "postgres": "Up 5 min",
                "api": "healthy",
            },
        ),
        patch("arasul_tui.commands.n8n_cmd.n8n_list_workflows", return_value=[]),
        patch("arasul_tui.commands.n8n_cmd._ensure_n8n_project"),
    ):
        result = cmd_n8n(state, [])
    assert result.ok is True
    assert result.style == "silent"


def test_n8n_stop_not_installed(state: TuiState):
    with patch("arasul_tui.commands.n8n_cmd.n8n_is_installed", return_value=False):
        result = cmd_n8n(state, ["stop"])
    assert result.ok is False


def test_n8n_stop_not_running(state: TuiState):
    with (
        patch("arasul_tui.commands.n8n_cmd.n8n_is_installed", return_value=True),
        patch("arasul_tui.commands.n8n_cmd.n8n_is_running", return_value=False),
    ):
        result = cmd_n8n(state, ["stop"])
    assert result.ok is True


def test_n8n_api_key_finish_saves_and_configures_mcp(state: TuiState):
    """API key wizard saves key and auto-configures MCP."""
    from arasul_tui.commands.n8n_cmd import _api_key_finish

    with (
        patch("arasul_tui.commands.n8n_cmd.n8n_save_api_key") as mock_save,
        patch("arasul_tui.commands.n8n_cmd.is_n8n_mcp_configured", return_value=False),
        patch("arasul_tui.commands.n8n_cmd.configure_n8n_mcp", return_value=(True, "done")),
        patch("arasul_tui.commands.n8n_cmd._ensure_n8n_project"),
    ):
        result = _api_key_finish(state, "  my-api-key-here  ")
    assert result.ok is True
    mock_save.assert_called_once_with("my-api-key-here")


def test_n8n_api_key_finish_empty(state: TuiState):
    from arasul_tui.commands.n8n_cmd import _api_key_finish

    result = _api_key_finish(state, "   ")
    assert result.ok is False


def test_n8n_unknown_subcommand_treated_as_smart_flow(state: TuiState):
    """Unknown subcommands fall through to smart flow, not an error."""
    with (
        patch("arasul_tui.commands.n8n_cmd.n8n_is_installed", return_value=True),
        patch("arasul_tui.commands.n8n_cmd.n8n_is_running", return_value=True),
        patch("arasul_tui.commands.n8n_cmd.n8n_get_api_key", return_value="key-123"),
        patch("arasul_tui.commands.n8n_cmd.is_n8n_mcp_configured", return_value=True),
        patch(
            "arasul_tui.commands.n8n_cmd.n8n_health",
            return_value={
                "container": "Up 5 min",
                "postgres": "Up 5 min",
                "api": "healthy",
            },
        ),
        patch("arasul_tui.commands.n8n_cmd.n8n_list_workflows", return_value=[]),
        patch("arasul_tui.commands.n8n_cmd._ensure_n8n_project"),
    ):
        result = cmd_n8n(state, ["foobar"])
    assert result.ok is True
