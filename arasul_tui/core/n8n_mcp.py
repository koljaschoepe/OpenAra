"""n8n MCP server configuration for Claude Code."""

from __future__ import annotations

from arasul_tui.core.claude_json import load_claude_json, save_claude_json
from arasul_tui.core.n8n_client import N8N_BASE_URL, n8n_get_api_key

MCP_SERVER_NAME = "n8n"


def is_n8n_mcp_configured() -> bool:
    """Check if n8n MCP server is configured in ~/.claude.json."""
    data = load_claude_json()
    return MCP_SERVER_NAME in data.get("mcpServers", {})


def get_n8n_mcp_config() -> dict | None:
    """Return current n8n MCP server config or None."""
    data = load_claude_json()
    return data.get("mcpServers", {}).get(MCP_SERVER_NAME)


def configure_n8n_mcp(api_key: str | None = None) -> tuple[bool, str]:
    """Add or update n8n MCP server in ~/.claude.json.

    Uses the API key from the argument or from the stored config.
    Returns (success, message).
    """
    key = api_key or n8n_get_api_key()
    if not key:
        return False, "No API key. Set one first with /n8n api-key"

    data = load_claude_json()
    if "mcpServers" not in data:
        data["mcpServers"] = {}

    data["mcpServers"][MCP_SERVER_NAME] = {
        "command": "npx",
        "args": ["-y", "n8n-mcp"],
        "env": {
            "N8N_API_URL": f"{N8N_BASE_URL}/api/v1",
            "N8N_API_KEY": key,
        },
    }

    try:
        save_claude_json(data)
    except OSError as exc:
        return False, f"Failed to save ~/.claude.json: {exc}"
    return True, "n8n MCP server configured in ~/.claude.json"


def remove_n8n_mcp() -> tuple[bool, str]:
    """Remove n8n MCP server from ~/.claude.json."""
    data = load_claude_json()
    if not data:
        return False, "~/.claude.json not found"

    servers = data.get("mcpServers", {})
    if MCP_SERVER_NAME not in servers:
        return False, "n8n MCP server not configured"

    del servers[MCP_SERVER_NAME]
    try:
        save_claude_json(data)
    except OSError as exc:
        return False, f"Failed to save ~/.claude.json: {exc}"
    return True, "n8n MCP server removed from ~/.claude.json"
