from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from arasul_tui.core.n8n_mcp import (
    configure_n8n_mcp,
    get_n8n_mcp_config,
    is_n8n_mcp_configured,
    remove_n8n_mcp,
)


def test_is_n8n_mcp_configured_false(tmp_path: Path):
    claude_json = tmp_path / ".claude.json"
    claude_json.write_text("{}")
    with patch("arasul_tui.core.claude_json.CLAUDE_JSON", claude_json):
        assert is_n8n_mcp_configured() is False


def test_is_n8n_mcp_configured_true(tmp_path: Path):
    claude_json = tmp_path / ".claude.json"
    claude_json.write_text(json.dumps({"mcpServers": {"n8n": {"command": "npx"}}}))
    with patch("arasul_tui.core.claude_json.CLAUDE_JSON", claude_json):
        assert is_n8n_mcp_configured() is True


def test_is_n8n_mcp_configured_no_file(tmp_path: Path):
    claude_json = tmp_path / ".claude.json"
    with patch("arasul_tui.core.claude_json.CLAUDE_JSON", claude_json):
        assert is_n8n_mcp_configured() is False


def test_get_n8n_mcp_config_none(tmp_path: Path):
    claude_json = tmp_path / ".claude.json"
    claude_json.write_text("{}")
    with patch("arasul_tui.core.claude_json.CLAUDE_JSON", claude_json):
        assert get_n8n_mcp_config() is None


def test_get_n8n_mcp_config_exists(tmp_path: Path):
    claude_json = tmp_path / ".claude.json"
    config = {"command": "npx", "args": ["-y", "n8n-mcp"]}
    claude_json.write_text(json.dumps({"mcpServers": {"n8n": config}}))
    with patch("arasul_tui.core.claude_json.CLAUDE_JSON", claude_json):
        result = get_n8n_mcp_config()
    assert result is not None
    assert result["command"] == "npx"


def test_configure_n8n_mcp_no_key(tmp_path: Path):
    claude_json = tmp_path / ".claude.json"
    claude_json.write_text("{}")
    with (
        patch("arasul_tui.core.claude_json.CLAUDE_JSON", claude_json),
        patch("arasul_tui.core.n8n_mcp.n8n_get_api_key", return_value=None),
    ):
        ok, msg = configure_n8n_mcp()
    assert ok is False
    assert "API key" in msg


def test_configure_n8n_mcp_with_key(tmp_path: Path):
    claude_json = tmp_path / ".claude.json"
    claude_json.write_text("{}")
    with patch("arasul_tui.core.claude_json.CLAUDE_JSON", claude_json):
        ok, msg = configure_n8n_mcp(api_key="test-key-123")
    assert ok is True

    data = json.loads(claude_json.read_text())
    assert "n8n" in data["mcpServers"]
    assert data["mcpServers"]["n8n"]["env"]["N8N_API_KEY"] == "test-key-123"
    assert "n8n-mcp" in data["mcpServers"]["n8n"]["args"]


def test_configure_n8n_mcp_preserves_existing(tmp_path: Path):
    claude_json = tmp_path / ".claude.json"
    existing = {"mcpServers": {"playwright": {"command": "npx"}}, "other": "value"}
    claude_json.write_text(json.dumps(existing))
    with patch("arasul_tui.core.claude_json.CLAUDE_JSON", claude_json):
        ok, _ = configure_n8n_mcp(api_key="my-key")
    assert ok is True

    data = json.loads(claude_json.read_text())
    assert "playwright" in data["mcpServers"]
    assert "n8n" in data["mcpServers"]
    assert data["other"] == "value"


def test_configure_n8n_mcp_no_file(tmp_path: Path):
    claude_json = tmp_path / ".claude.json"
    with patch("arasul_tui.core.claude_json.CLAUDE_JSON", claude_json):
        ok, _ = configure_n8n_mcp(api_key="fresh-key")
    assert ok is True
    assert claude_json.exists()

    data = json.loads(claude_json.read_text())
    assert "n8n" in data["mcpServers"]


def test_remove_n8n_mcp_success(tmp_path: Path):
    claude_json = tmp_path / ".claude.json"
    claude_json.write_text(json.dumps({"mcpServers": {"n8n": {"command": "npx"}}}))
    with patch("arasul_tui.core.claude_json.CLAUDE_JSON", claude_json):
        ok, msg = remove_n8n_mcp()
    assert ok is True

    data = json.loads(claude_json.read_text())
    assert "n8n" not in data.get("mcpServers", {})


def test_remove_n8n_mcp_not_configured(tmp_path: Path):
    claude_json = tmp_path / ".claude.json"
    claude_json.write_text(json.dumps({"mcpServers": {}}))
    with patch("arasul_tui.core.claude_json.CLAUDE_JSON", claude_json):
        ok, msg = remove_n8n_mcp()
    assert ok is False


def test_remove_n8n_mcp_no_file(tmp_path: Path):
    claude_json = tmp_path / ".claude.json"
    with patch("arasul_tui.core.claude_json.CLAUDE_JSON", claude_json):
        ok, msg = remove_n8n_mcp()
    assert ok is False
