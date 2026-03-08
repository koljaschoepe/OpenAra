from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

from arasul_tui.core.browser import (
    _browsers_path,
    browser_health,
    browser_test,
    configure_mcp,
    ensure_browser,
    install_browser,
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


def test_is_playwright_installed_true():
    import sys
    import types

    mock_mod = types.ModuleType("playwright")
    with patch.dict(sys.modules, {"playwright": mock_mod}):
        assert is_playwright_installed() is True


def test_is_playwright_installed_false():
    import sys

    # Setting a module to None in sys.modules causes import to raise ImportError
    with patch.dict(sys.modules, {"playwright": None}):
        assert is_playwright_installed() is False


# ---------------------------------------------------------------------------
# ensure_browser() tests (10.2)
# ---------------------------------------------------------------------------


def test_ensure_browser_both_ok():
    with (
        patch("arasul_tui.core.browser.is_playwright_installed", return_value=True),
        patch("arasul_tui.core.browser.is_chromium_installed", return_value=True),
    ):
        ok, msg = ensure_browser()
    assert ok is True
    assert "ready" in msg.lower()


def test_ensure_browser_no_playwright():
    with patch("arasul_tui.core.browser.is_playwright_installed", return_value=False):
        ok, msg = ensure_browser()
    assert ok is False
    assert "Playwright" in msg


def test_ensure_browser_no_chromium():
    with (
        patch("arasul_tui.core.browser.is_playwright_installed", return_value=True),
        patch("arasul_tui.core.browser.is_chromium_installed", return_value=False),
    ):
        ok, msg = ensure_browser()
    assert ok is False
    assert "Chromium" in msg


# ---------------------------------------------------------------------------
# browser_health() tests (10.2)
# ---------------------------------------------------------------------------


def test_browser_health_all_installed(tmp_path: Path):
    import sys
    import types

    mock_mod = types.ModuleType("playwright")
    mock_mod.__version__ = "1.40.0"
    chrome = tmp_path / "chromium-1234" / "chrome-linux" / "chrome"
    chrome.parent.mkdir(parents=True)
    chrome.write_bytes(b"fake")
    chrome.chmod(0o755)
    with (
        patch.dict(sys.modules, {"playwright": mock_mod}),
        patch("arasul_tui.core.browser._browsers_path", return_value=tmp_path),
        patch("arasul_tui.core.browser.is_mcp_configured", return_value=True),
    ):
        rows = browser_health()
    keys = [r[0] for r in rows]
    assert "Playwright" in keys
    assert "Chromium" in keys
    assert "MCP Server" in keys


def test_browser_health_nothing_installed(tmp_path: Path):
    import sys

    with (
        patch.dict(sys.modules, {"playwright": None}),
        patch("arasul_tui.core.browser._browsers_path", return_value=tmp_path / "nonexistent"),
        patch("arasul_tui.core.browser.is_mcp_configured", return_value=False),
    ):
        rows = browser_health()
    # Should still return rows without crashing
    assert len(rows) >= 3


# ---------------------------------------------------------------------------
# browser_test() tests (10.2)
# ---------------------------------------------------------------------------


def test_browser_test_not_ready():
    with patch("arasul_tui.core.browser.ensure_browser", return_value=(False, "Not installed")):
        ok, lines = browser_test()
    assert ok is False
    assert "Not installed" in lines[0]


def test_browser_test_success(tmp_path: Path):
    mock_result = type("R", (), {"returncode": 0, "stdout": "OK\n", "stderr": ""})()
    with (
        patch("arasul_tui.core.browser.ensure_browser", return_value=(True, "OK")),
        patch("arasul_tui.core.browser._browsers_path", return_value=tmp_path),
        patch("arasul_tui.core.browser.subprocess") as mock_sub,
    ):
        mock_sub.run.return_value = mock_result
        mock_sub.TimeoutExpired = subprocess.TimeoutExpired
        ok, lines = browser_test()
    assert ok is True


def test_browser_test_failure(tmp_path: Path):
    mock_result = type("R", (), {"returncode": 1, "stdout": "", "stderr": "crash"})()
    with (
        patch("arasul_tui.core.browser.ensure_browser", return_value=(True, "OK")),
        patch("arasul_tui.core.browser._browsers_path", return_value=tmp_path),
        patch("arasul_tui.core.browser.subprocess") as mock_sub,
    ):
        mock_sub.run.return_value = mock_result
        mock_sub.TimeoutExpired = subprocess.TimeoutExpired
        ok, lines = browser_test()
    assert ok is False


def test_browser_test_timeout(tmp_path: Path):
    with (
        patch("arasul_tui.core.browser.ensure_browser", return_value=(True, "OK")),
        patch("arasul_tui.core.browser._browsers_path", return_value=tmp_path),
        patch("arasul_tui.core.browser.subprocess") as mock_sub,
    ):
        mock_sub.run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=30)
        mock_sub.TimeoutExpired = subprocess.TimeoutExpired
        ok, lines = browser_test()
    assert ok is False
    assert "timeout" in lines[0].lower()


# ---------------------------------------------------------------------------
# install_browser() tests (10.2)
# ---------------------------------------------------------------------------


def test_install_browser_success(tmp_path: Path):
    ok_result = type("R", (), {"returncode": 0, "stdout": "done", "stderr": ""})()
    with (
        patch("arasul_tui.core.browser.is_playwright_installed", return_value=True),
        patch("arasul_tui.core.browser._browsers_path", return_value=tmp_path),
        patch("arasul_tui.core.browser.subprocess") as mock_sub,
    ):
        mock_sub.run.return_value = ok_result
        ok, lines = install_browser()
    assert ok is True
    assert any("Chromium" in line for line in lines)


def test_install_browser_pip_fail(tmp_path: Path):
    fail_result = type("R", (), {"returncode": 1, "stdout": "", "stderr": "pip error"})()
    with (
        patch("arasul_tui.core.browser.is_playwright_installed", return_value=False),
        patch("arasul_tui.core.browser._browsers_path", return_value=tmp_path),
        patch("arasul_tui.core.browser.subprocess") as mock_sub,
    ):
        mock_sub.run.return_value = fail_result
        ok, lines = install_browser()
    assert ok is False
