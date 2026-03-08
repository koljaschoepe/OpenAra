"""Command handlers package — re-exports all handlers for backward compatibility."""

from __future__ import annotations

from arasul_tui.commands.ai import cmd_auth, cmd_claude
from arasul_tui.commands.browser_cmd import cmd_browser
from arasul_tui.commands.expose_cmd import cmd_expose
from arasul_tui.commands.git_ops import cmd_git
from arasul_tui.commands.mcp import cmd_mcp
from arasul_tui.commands.meta import cmd_exit, cmd_help, cmd_welcome
from arasul_tui.commands.n8n_cmd import cmd_n8n
from arasul_tui.commands.project import (
    _clone_finish,
    _create_finish,
    _delete_confirm,
    _delete_select,
    cmd_clone,
    cmd_create,
    cmd_delete,
    cmd_info,
    cmd_open,
    cmd_repos,
)
from arasul_tui.commands.security import cmd_keys, cmd_logins, cmd_security
from arasul_tui.commands.system import cmd_docker, cmd_health, cmd_setup, cmd_status
from arasul_tui.commands.tailscale_cmd import cmd_tailscale

__all__ = [
    # Project
    "cmd_open",
    "cmd_create",
    "cmd_clone",
    "cmd_delete",
    "cmd_info",
    "cmd_repos",
    "_create_finish",
    "_clone_finish",
    "_delete_confirm",
    "_delete_select",
    # AI
    "cmd_claude",
    "cmd_auth",
    # Git
    "cmd_git",
    # System
    "cmd_status",
    "cmd_health",
    "cmd_setup",
    "cmd_docker",
    # Security
    "cmd_keys",
    "cmd_logins",
    "cmd_security",
    # Browser
    "cmd_browser",
    # MCP
    "cmd_mcp",
    # Expose
    "cmd_expose",
    # Tailscale
    "cmd_tailscale",
    # n8n
    "cmd_n8n",
    # Meta
    "cmd_help",
    "cmd_exit",
    "cmd_welcome",
]
