from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from arasul_tui.commands.mcp import cmd_mcp
from arasul_tui.core.router import REGISTRY
from arasul_tui.core.state import TuiState


def _state() -> TuiState:
    return TuiState(registry=REGISTRY)


def test_mcp_list_empty(tmp_path: Path):
    claude_json = tmp_path / ".claude.json"
    claude_json.write_text("{}", encoding="utf-8")
    with patch("arasul_tui.core.claude_json.CLAUDE_JSON", claude_json):
        result = cmd_mcp(_state(), ["list"])
    assert result.ok is True


def test_mcp_list_with_servers(tmp_path: Path):
    claude_json = tmp_path / ".claude.json"
    data = {"mcpServers": {"test-server": {"command": "npx", "args": ["-y", "test"]}}}
    claude_json.write_text(json.dumps(data), encoding="utf-8")
    with patch("arasul_tui.core.claude_json.CLAUDE_JSON", claude_json):
        result = cmd_mcp(_state(), ["list"])
    assert result.ok is True


def test_mcp_add_missing_args():
    result = cmd_mcp(_state(), ["add"])
    assert result.ok is False


def test_mcp_add_success(tmp_path: Path):
    claude_json = tmp_path / ".claude.json"
    claude_json.write_text("{}", encoding="utf-8")
    with patch("arasul_tui.core.claude_json.CLAUDE_JSON", claude_json):
        result = cmd_mcp(_state(), ["add", "my-server", "npx", "-y", "pkg"])
    assert result.ok is True
    data = json.loads(claude_json.read_text())
    assert "my-server" in data["mcpServers"]
    assert data["mcpServers"]["my-server"]["command"] == "npx"


def test_mcp_remove_missing_args():
    result = cmd_mcp(_state(), ["remove"])
    assert result.ok is False


def test_mcp_remove_not_found(tmp_path: Path):
    claude_json = tmp_path / ".claude.json"
    claude_json.write_text('{"mcpServers": {}}', encoding="utf-8")
    with patch("arasul_tui.core.claude_json.CLAUDE_JSON", claude_json):
        result = cmd_mcp(_state(), ["remove", "nonexistent"])
    assert result.ok is False


def test_mcp_remove_success(tmp_path: Path):
    claude_json = tmp_path / ".claude.json"
    data = {"mcpServers": {"srv": {"command": "test"}}}
    claude_json.write_text(json.dumps(data), encoding="utf-8")
    with patch("arasul_tui.core.claude_json.CLAUDE_JSON", claude_json):
        result = cmd_mcp(_state(), ["remove", "srv"])
    assert result.ok is True
    updated = json.loads(claude_json.read_text())
    assert "srv" not in updated.get("mcpServers", {})


def test_mcp_unknown_subcommand():
    result = cmd_mcp(_state(), ["bogus"])
    assert result.ok is False


def test_mcp_default_is_list(tmp_path: Path):
    claude_json = tmp_path / ".claude.json"
    claude_json.write_text("{}", encoding="utf-8")
    with patch("arasul_tui.core.claude_json.CLAUDE_JSON", claude_json):
        result = cmd_mcp(_state(), [])
    assert result.ok is True
