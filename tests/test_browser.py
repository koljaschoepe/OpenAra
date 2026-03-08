from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

from arasul_tui.core.browser import (
    _browsers_path,
    configure_mcp,
    is_mcp_configured,
    is_playwright_installed,
)


def test_browsers_path_from_env(tmp_path: Path):
    custom = str(tmp_path / "custom-browsers")
    with patch.dict(os.environ, {"PLAYWRIGHT_BROWSERS_PATH": custom}):
        assert _browsers_path() == Path(custom)


def test_browsers_path_external_storage(tmp_path: Path):
    cache = tmp_path / "playwright-browsers"
    cache.mkdir()
    with (
        patch.dict(os.environ, {}, clear=True),
        patch("arasul_tui.core.browser._storage_browser_cache", return_value=cache),
    ):
        os.environ.pop("PLAYWRIGHT_BROWSERS_PATH", None)
        assert _browsers_path() == cache


def test_browsers_path_fallback(tmp_path: Path):
    nonexistent = tmp_path / "nonexistent"
    fallback = tmp_path / "fallback-cache"
    with (
        patch.dict(os.environ, {}, clear=True),
        patch("arasul_tui.core.browser._storage_browser_cache", return_value=nonexistent),
        patch("arasul_tui.core.browser.FALLBACK_BROWSER_CACHE", fallback),
    ):
        os.environ.pop("PLAYWRIGHT_BROWSERS_PATH", None)
        assert _browsers_path() == fallback


def test_is_mcp_configured_no_file(tmp_path: Path):
    claude_json = tmp_path / ".claude.json"
    with patch("arasul_tui.core.claude_json.CLAUDE_JSON", claude_json):
        assert is_mcp_configured() is False


def test_is_mcp_configured_no_playwright(tmp_path: Path):
    claude_json = tmp_path / ".claude.json"
    claude_json.write_text('{"mcpServers": {}}', encoding="utf-8")
    with patch("arasul_tui.core.claude_json.CLAUDE_JSON", claude_json):
        assert is_mcp_configured() is False


def test_is_mcp_configured_with_playwright(tmp_path: Path):
    claude_json = tmp_path / ".claude.json"
    data = {"mcpServers": {"playwright": {"command": "npx"}}}
    claude_json.write_text(json.dumps(data), encoding="utf-8")
    with patch("arasul_tui.core.claude_json.CLAUDE_JSON", claude_json):
        assert is_mcp_configured() is True


def test_configure_mcp_creates_entry(tmp_path: Path):
    claude_json = tmp_path / ".claude.json"
    with (
        patch("arasul_tui.core.claude_json.CLAUDE_JSON", claude_json),
        patch("arasul_tui.core.browser._browsers_path", return_value=tmp_path / "browsers"),
    ):
        ok, msg = configure_mcp()
        assert ok is True
        data = json.loads(claude_json.read_text())
        assert "playwright" in data["mcpServers"]
        assert data["mcpServers"]["playwright"]["command"] == "npx"


def test_configure_mcp_preserves_existing(tmp_path: Path):
    claude_json = tmp_path / ".claude.json"
    existing = {"someKey": "someValue", "mcpServers": {"other": {"command": "test"}}}
    claude_json.write_text(json.dumps(existing), encoding="utf-8")
    with (
        patch("arasul_tui.core.claude_json.CLAUDE_JSON", claude_json),
        patch("arasul_tui.core.browser._browsers_path", return_value=tmp_path / "browsers"),
    ):
        ok, msg = configure_mcp()
        assert ok is True
        data = json.loads(claude_json.read_text())
        assert data["someKey"] == "someValue"
        assert "other" in data["mcpServers"]
        assert "playwright" in data["mcpServers"]


def test_is_playwright_installed():
    # Just verify it returns a bool without crashing
    result = is_playwright_installed()
    assert isinstance(result, bool)
