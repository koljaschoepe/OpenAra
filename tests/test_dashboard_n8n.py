"""Tests for n8n section in project screen dashboard."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from arasul_tui.core.n8n_client import N8nAccessInfo
from arasul_tui.core.state import TuiState
from arasul_tui.core.ui.dashboard import _print_project_screen


def _make_access(
    is_running: bool = True,
    tailscale_url: str = "",
) -> N8nAccessInfo:
    return N8nAccessInfo(
        is_running=is_running,
        hostname="myjetson",
        tailscale_url=tailscale_url,
        ssh_tunnel_cmd="ssh -L 5678:localhost:5678 myjetson",
        local_url="http://localhost:5678",
    )


def _capture_project_screen(state, **extra_patches) -> str:
    """Run _print_project_screen and capture all printed output."""
    printed: list[str] = []
    mock_con = MagicMock()
    mock_con.print = lambda *a, **kw: printed.append(str(a[0]) if a else "")

    base_patches = {
        "arasul_tui.core.git_info.get_git_info": None,
        "arasul_tui.core.git_info.detect_language": "",
        "arasul_tui.core.git_info.get_disk_usage": "",
    }
    base_patches.update(extra_patches)

    # Build context managers
    import contextlib

    with contextlib.ExitStack() as stack:
        stack.enter_context(patch("arasul_tui.core.ui.dashboard.console", mock_con))
        for target, val in base_patches.items():
            stack.enter_context(patch(target, return_value=val))
        _print_project_screen(state)

    return "\n".join(printed)


def test_project_screen_n8n_running(state: TuiState):
    """n8n running should show green status."""
    state.active_project = Path("/tmp/projects/n8n-workflows")
    output = _capture_project_screen(
        state,
        **{
            "arasul_tui.core.n8n_project.is_n8n_project_name": True,
            "arasul_tui.core.n8n_client.n8n_is_installed": True,
            "arasul_tui.core.n8n_client.n8n_access_info": _make_access(is_running=True),
        },
    )
    assert "n8n running" in output


def test_project_screen_n8n_stopped(state: TuiState):
    """n8n stopped should show warning status."""
    state.active_project = Path("/tmp/projects/n8n-workflows")
    output = _capture_project_screen(
        state,
        **{
            "arasul_tui.core.n8n_project.is_n8n_project_name": True,
            "arasul_tui.core.n8n_client.n8n_is_installed": True,
            "arasul_tui.core.n8n_client.n8n_access_info": _make_access(is_running=False),
        },
    )
    assert "n8n stopped" in output


def test_project_screen_n8n_with_tailscale(state: TuiState):
    """When Tailscale URL is available, show it instead of SSH tunnel."""
    state.active_project = Path("/tmp/projects/n8n-workflows")
    output = _capture_project_screen(
        state,
        **{
            "arasul_tui.core.n8n_project.is_n8n_project_name": True,
            "arasul_tui.core.n8n_client.n8n_is_installed": True,
            "arasul_tui.core.n8n_client.n8n_access_info": _make_access(
                tailscale_url="https://myjetson.ts.net",
            ),
        },
    )
    assert "https://myjetson.ts.net" in output
    assert "ssh -L" not in output


def test_project_screen_n8n_ssh_tunnel(state: TuiState):
    """Without Tailscale, show SSH tunnel command."""
    state.active_project = Path("/tmp/projects/n8n-workflows")
    output = _capture_project_screen(
        state,
        **{
            "arasul_tui.core.n8n_project.is_n8n_project_name": True,
            "arasul_tui.core.n8n_client.n8n_is_installed": True,
            "arasul_tui.core.n8n_client.n8n_access_info": _make_access(),
        },
    )
    assert "ssh -L 5678:localhost:5678 myjetson" in output
    assert "http://localhost:5678" in output


def test_project_screen_non_n8n(state: TuiState):
    """Regular project should not show n8n section."""
    state.active_project = Path("/tmp/projects/my-app")
    output = _capture_project_screen(state)
    assert "n8n running" not in output
    assert "n8n stopped" not in output


def test_project_screen_n8n_not_installed(state: TuiState):
    """n8n project name but n8n not installed should not show n8n section."""
    state.active_project = Path("/tmp/projects/n8n-workflows")
    output = _capture_project_screen(
        state,
        **{
            "arasul_tui.core.n8n_project.is_n8n_project_name": True,
            "arasul_tui.core.n8n_client.n8n_is_installed": False,
        },
    )
    assert "n8n running" not in output
    assert "n8n stopped" not in output
