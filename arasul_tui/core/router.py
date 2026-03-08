from __future__ import annotations

import shlex

from arasul_tui.commands import (
    cmd_auth,
    cmd_browser,
    cmd_claude,
    cmd_clone,
    cmd_create,
    cmd_delete,
    cmd_docker,
    cmd_exit,
    cmd_expose,
    cmd_git,
    cmd_health,
    cmd_help,
    cmd_info,
    cmd_keys,
    cmd_logins,
    cmd_mcp,
    cmd_n8n,
    cmd_open,
    cmd_repos,
    cmd_security,
    cmd_setup,
    cmd_status,
    cmd_tailscale,
    cmd_welcome,
)
from arasul_tui.core.registry import CommandRegistry, CommandSpec
from arasul_tui.core.state import TuiState
from arasul_tui.core.types import CommandResult
from arasul_tui.core.ui import print_error, print_info, print_warning


def build_registry() -> CommandRegistry:
    reg = CommandRegistry()

    # Projects
    reg.register(
        CommandSpec(
            "open",
            cmd_open,
            "Open project",
            category="Projects",
            aliases=["open project", "switch"],
        )
    )
    reg.register(
        CommandSpec(
            "create",
            cmd_create,
            "Create project",
            category="Projects",
            aliases=["new", "new project", "create project"],
        )
    )
    reg.register(
        CommandSpec(
            "clone",
            cmd_clone,
            "Clone repo",
            category="Projects",
            aliases=["clone repo", "git clone"],
        )
    )
    reg.register(
        CommandSpec(
            "delete",
            cmd_delete,
            "Delete project",
            category="Projects",
            aliases=["remove", "remove project", "delete project"],
        )
    )
    reg.register(
        CommandSpec(
            "info",
            cmd_info,
            "Project details",
            category="Projects",
            aliases=["details", "project info", "about"],
        )
    )
    reg.register(
        CommandSpec(
            "repos",
            cmd_repos,
            "All projects",
            category="Projects",
            aliases=["projects", "list", "all projects", "show projects"],
        )
    )

    # Claude Code
    reg.register(
        CommandSpec(
            "claude",
            cmd_claude,
            "Start Claude",
            category="Claude Code",
            aliases=["ai", "start claude", "claude code"],
        )
    )
    reg.register(
        CommandSpec(
            "auth",
            cmd_auth,
            "Auth & tools",
            category="Claude Code",
            aliases=["login", "authentication", "tools"],
        )
    )

    # Git
    reg.register(
        CommandSpec(
            "git",
            cmd_git,
            "GitHub setup / git ops",
            category="Git",
            aliases=["github", "pull", "push"],
            subcommands={
                "pull": "Pull project",
                "push": "Push project",
                "log": "Recent commits",
                "status": "Working tree",
            },
        )
    )

    # System
    reg.register(
        CommandSpec(
            "status",
            cmd_status,
            "System status",
            category="System",
            aliases=["system", "sys", "system status", "how is the system"],
        )
    )
    reg.register(
        CommandSpec(
            "health",
            cmd_health,
            "Health diagnostic",
            category="System",
            aliases=["diagnostics", "check", "health check", "system health"],
        )
    )
    reg.register(
        CommandSpec(
            "setup",
            cmd_setup,
            "Setup wizard",
            category="System",
            aliases=["install", "wizard", "setup wizard"],
        )
    )
    reg.register(
        CommandSpec(
            "docker",
            cmd_docker,
            "Container status",
            category="System",
            aliases=["containers", "container status"],
        )
    )

    # Security
    reg.register(
        CommandSpec(
            "keys",
            cmd_keys,
            "SSH keys",
            category="Security",
            aliases=["ssh keys", "ssh"],
        )
    )
    reg.register(
        CommandSpec(
            "logins",
            cmd_logins,
            "Recent logins",
            category="Security",
            aliases=["login history", "who logged in", "recent logins"],
        )
    )
    reg.register(
        CommandSpec(
            "security",
            cmd_security,
            "Security audit",
            category="Security",
            aliases=["audit", "security check", "am i safe", "secure"],
        )
    )

    # Browser
    reg.register(
        CommandSpec(
            "browser",
            cmd_browser,
            "Headless browser",
            category="Browser",
            aliases=["chromium", "playwright"],
            subcommands={
                "test": "Connection test",
            },
        )
    )

    # MCP
    reg.register(
        CommandSpec(
            "mcp",
            cmd_mcp,
            "MCP servers",
            category="MCP",
            aliases=["servers", "mcp servers"],
            subcommands={
                "list": "List servers",
                "add": "Add server",
                "test": "Test servers",
                "remove": "Remove server",
            },
        )
    )

    # Services
    reg.register(
        CommandSpec(
            "n8n",
            cmd_n8n,
            "Workflow automation",
            category="Services",
            aliases=["workflows", "automation"],
            subcommands={
                "stop": "Stop containers",
            },
        )
    )

    # Expose
    reg.register(
        CommandSpec(
            "expose",
            cmd_expose,
            "Public URL (Funnel)",
            category="Network",
            aliases=["funnel", "public url", "make public"],
            subcommands={
                "status": "Funnel status",
                "on": "Start public URL",
                "off": "Stop public URL",
            },
        )
    )

    # Network
    reg.register(
        CommandSpec(
            "tailscale",
            cmd_tailscale,
            "VPN remote access",
            category="Network",
            aliases=["vpn", "network", "remote access"],
            subcommands={
                "status": "Connection status",
                "install": "Install Tailscale",
                "up": "Connect",
                "down": "Disconnect",
            },
        )
    )

    # Meta
    reg.register(
        CommandSpec(
            "help",
            cmd_help,
            "Show help",
            category="Meta",
            aliases=["?", "commands", "what can you do"],
        )
    )
    reg.register(
        CommandSpec(
            "exit",
            cmd_exit,
            "Quit",
            category="Meta",
            aliases=["quit", "bye", "goodbye", "q"],
        )
    )
    reg.register(
        CommandSpec(
            "welcome",
            cmd_welcome,
            "Re-run onboarding wizard",
            category="Meta",
        )
    )

    return reg


REGISTRY = build_registry()


def run_command(state: TuiState, raw: str) -> CommandResult:
    """Route input to the appropriate command handler.

    Accepts both slash commands (/status) and natural language (status, system, etc.).
    """
    text = raw.strip()
    if not text:
        return CommandResult(ok=True, style="silent")

    # Slash commands: parse traditionally
    if text.startswith("/"):
        try:
            parts = shlex.split(text[1:])
        except ValueError as exc:
            print_error(f"Parse error: {exc}")
            return CommandResult(ok=False, style="silent")

        if not parts:
            return CommandResult(ok=True, style="silent")

        cmd, args = parts[0].lower(), parts[1:]
        spec = REGISTRY.get(cmd)
        if spec:
            return spec.handler(state, args)

        prefixes = [name for name in REGISTRY.names() if name.startswith(cmd)]
        if len(prefixes) == 1:
            # Auto-execute the unique prefix match
            matched = REGISTRY.get(prefixes[0])
            if matched:
                return matched.handler(state, args)
        elif prefixes:
            hint = ", ".join(f"[bold]{p}[/bold]" for p in prefixes[:3])
            print_info(f"Did you mean: {hint}? [dim](Tab to complete)[/dim]")
        else:
            print_warning(f"I don't know '[bold]{cmd}[/bold]'. Try [bold]help[/bold] for all commands.")
        return CommandResult(ok=False, style="silent")

    # Natural language: resolve via alias/fuzzy matching
    spec, args = REGISTRY.resolve(text)
    if spec:
        return spec.handler(state, args)

    # No match found
    print_warning(f"Hmm, I don't know '[bold]{text}[/bold]'. Try [bold]help[/bold] to see what I can do.")
    return CommandResult(ok=False, style="silent")
