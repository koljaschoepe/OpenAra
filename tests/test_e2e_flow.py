"""End-to-end tests — simulate full user sessions through the dispatch loop.

Strategy: These are the highest-level tests. Each test exercises a complete
user workflow (create → open → info → delete) through run_command(),
mimicking app.py without starting the interactive event loop.

Routing-level tests (slash vs natural language, aliases, prefix matching)
live in test_router.py. Individual command tests live in their own files.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from arasul_tui.core.router import run_command
from arasul_tui.core.state import Screen, TuiState
from tests.conftest import make_platform, mock_platform

_GENERIC = make_platform(name="generic", model="test-machine")


# ---------------------------------------------------------------------------
# E2E Test 1: Full project lifecycle — create, open, info, delete
# ---------------------------------------------------------------------------


class TestFullProjectLifecycle:
    """Gold-standard E2E: user creates a project, opens it, views info, deletes it."""

    def test_create_view_delete(self, state: TuiState):
        tmp_path = state.project_root
        with mock_platform(_GENERIC):
            # Create project
            with patch("arasul_tui.commands.project.is_miniforge_installed", return_value=False):
                result = run_command(state, "create my-test-project")
            assert result.ok is True
            assert (tmp_path / "my-test-project").exists()

            # Open project
            result = run_command(state, "open my-test-project")
            assert result.ok is True
            assert state.active_project is not None
            assert state.active_project.name == "my-test-project"

            # View info (simulate app.py screen transition)
            state.screen = Screen.PROJECT
            result = run_command(state, "/info")
            assert result.ok is True

            # Go back and delete (wizard: select number → confirm)
            state.screen = Screen.MAIN
            state.active_project = None

            result = run_command(state, "delete")
            assert result.ok is True
            assert result.pending_handler is not None

            result = result.pending_handler(state, "1")
            assert result.ok is True
            assert result.pending_handler is not None

            result = result.pending_handler(state, "y")
            assert result.ok is True
            assert not (tmp_path / "my-test-project").exists()


# ---------------------------------------------------------------------------
# E2E Test 2: Command chains — multiple commands in sequence
# ---------------------------------------------------------------------------


class TestCommandChains:
    """Verify related commands work correctly when run in sequence."""

    def test_security_commands_chain(self, state: TuiState):
        """All three security commands succeed when run back-to-back."""
        with (
            patch("arasul_tui.commands.security.list_ssh_keys", return_value=[]),
            patch("arasul_tui.commands.security.recent_logins", return_value=["test login"]),
            patch("arasul_tui.commands.security.security_audit", return_value=[]),
        ):
            r1 = run_command(state, "/keys")
            r2 = run_command(state, "/logins")
            r3 = run_command(state, "/security")
        assert all(r.ok for r in [r1, r2, r3])

    def test_system_commands_chain(self, state: TuiState):
        """Status, health, docker all succeed when run back-to-back."""
        with (
            patch("arasul_tui.commands.system.run_cmd", return_value=""),
            patch("arasul_tui.commands.system.list_containers", return_value=[]),
            patch("arasul_tui.commands.system.docker_running_count", return_value=0),
        ):
            r1 = run_command(state, "/status")
            r2 = run_command(state, "/health")
            r3 = run_command(state, "/docker")
        assert all(r.ok for r in [r1, r2, r3])


# ---------------------------------------------------------------------------
# E2E Test 3: Wizard state machine — multi-step flows
# ---------------------------------------------------------------------------


class TestWizardFlow:
    """Test wizard state machine transitions via pending_handler chaining."""

    def test_setup_wizard_invalid_then_valid(self, state: TuiState):
        """Setup wizard re-prompts on invalid input."""
        from arasul_tui.commands.system import cmd_setup

        with patch("arasul_tui.commands.system.check_setup_status") as mock:
            step = MagicMock()
            step.name = "Network"
            step.number = 2
            step.description = "Configure network"
            mock.return_value = [(step, False)]

            result = cmd_setup(state, [])
            assert result.ok is True
            assert result.pending_handler is not None
            assert result.prompt == "Step"

            # Invalid input keeps wizard alive
            result2 = result.pending_handler(state, "abc")
            assert result2.ok is False
            assert result2.pending_handler is not None

    def test_git_wizard_rejects_empty_token(self, state: TuiState):
        """Git auth wizard rejects empty token and re-prompts."""
        from arasul_tui.commands.git_ops import _git_wizard_auth_token

        result = _git_wizard_auth_token(state, "")
        assert result.ok is False
        assert result.pending_handler is not None
