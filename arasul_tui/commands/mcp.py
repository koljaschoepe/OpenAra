from __future__ import annotations

import shlex

from arasul_tui.core.claude_json import load_claude_json, save_claude_json
from arasul_tui.core.shell import run_cmd
from arasul_tui.core.state import TuiState
from arasul_tui.core.types import CommandResult
from arasul_tui.core.ui import (
    content_width,
    print_error,
    print_info,
    print_styled_panel,
    print_success,
    suggest_next,
    truncate,
)


def cmd_mcp(state: TuiState, args: list[str]) -> CommandResult:
    """MCP server management."""
    sub = args[0] if args else "list"

    if sub == "list":
        data = load_claude_json()
        servers = data.get("mcpServers", {})
        if not servers:
            print_info("No MCP servers configured.")
            suggest_next(
                "[bold]/browser[/bold]  → Browse the web (Playwright)",
                "[bold]/n8n[/bold]      → Workflow automation",
                "[bold]/mcp add[/bold]  → Add a custom server",
            )
            return CommandResult(ok=True, style="silent")

        cw = content_width()
        rows: list[tuple[str, str]] = []
        for name, config in servers.items():
            cmd = config.get("command", "?")
            cmd_args = " ".join(config.get("args", []))
            rows.append((name, truncate(f"{cmd} {cmd_args}", cw)))

        print_styled_panel("MCP Servers", rows)
        return CommandResult(ok=True, style="silent")

    if sub == "add":
        if len(args) < 3:
            print_error("Usage: [bold]/mcp add <name> <command> [args...][/bold]")
            return CommandResult(ok=False, style="silent")

        name = args[1]
        command = args[2]
        cmd_args = args[3:] if len(args) > 3 else []

        data = load_claude_json()
        if "mcpServers" not in data:
            data["mcpServers"] = {}

        data["mcpServers"][name] = {
            "command": command,
            "args": cmd_args,
        }
        save_claude_json(data)
        print_success(f"MCP server added: [bold]{name}[/bold]")
        suggest_next(f"Verify: [bold]/mcp test {name}[/bold]")
        return CommandResult(ok=True, style="silent")

    if sub == "test":
        name = args[1] if len(args) > 1 else None
        data = load_claude_json()
        servers = data.get("mcpServers", {})

        if not servers:
            print_info("No MCP servers configured.")
            return CommandResult(ok=True, style="silent")

        if name and name not in servers:
            print_error(f"MCP server not found: [bold]{name}[/bold]")
            return CommandResult(ok=False, style="silent")

        targets = {name: servers[name]} if name else servers
        rows: list[tuple[str, str]] = []
        for srv_name, config in targets.items():
            cmd = config.get("command", "")
            check = run_cmd(f"command -v {shlex.quote(cmd)} 2>/dev/null", timeout=3)
            if check and not check.startswith("Error"):
                rows.append((srv_name, f"[green]✓[/green] {cmd} found"))
            else:
                rows.append((srv_name, f"[red]✗[/red] {cmd} not found"))

        print_styled_panel("MCP Server Check", rows)
        return CommandResult(ok=True, style="silent")

    if sub == "remove":
        if len(args) < 2:
            print_error("Usage: [bold]/mcp remove <name>[/bold]")
            return CommandResult(ok=False, style="silent")

        name = args[1]
        data = load_claude_json()
        servers = data.get("mcpServers", {})
        if name not in servers:
            print_error(f"MCP server not found: [bold]{name}[/bold]")
            return CommandResult(ok=False, style="silent")

        del servers[name]
        save_claude_json(data)
        print_success(f"MCP server removed: [bold]{name}[/bold]")
        return CommandResult(ok=True, style="silent")

    print_error(f"Unknown subcommand: [bold]{sub}[/bold]")
    print_info("Available: [bold]list[/bold], [bold]add[/bold], [bold]test[/bold], [bold]remove[/bold]")
    return CommandResult(ok=False, style="silent")
