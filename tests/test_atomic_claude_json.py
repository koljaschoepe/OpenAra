"""Test atomic writes for ~/.claude.json."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from arasul_tui.core.claude_json import load_claude_json, save_claude_json


def test_save_creates_file(tmp_path, monkeypatch):
    """save_claude_json creates the file if it doesn't exist."""
    target = tmp_path / ".claude.json"
    monkeypatch.setattr("arasul_tui.core.claude_json.CLAUDE_JSON", target)
    save_claude_json({"mcpServers": {}})
    assert target.exists()
    data = json.loads(target.read_text())
    assert data == {"mcpServers": {}}


def test_save_overwrites_existing(tmp_path, monkeypatch):
    """save_claude_json overwrites existing file atomically."""
    target = tmp_path / ".claude.json"
    target.write_text('{"old": true}')
    monkeypatch.setattr("arasul_tui.core.claude_json.CLAUDE_JSON", target)
    save_claude_json({"new": True})
    data = json.loads(target.read_text())
    assert data == {"new": True}


def test_save_no_tmp_leftover_on_success(tmp_path, monkeypatch):
    """No temp files left behind after successful write."""
    target = tmp_path / ".claude.json"
    monkeypatch.setattr("arasul_tui.core.claude_json.CLAUDE_JSON", target)
    save_claude_json({"test": 1})
    tmp_files = list(tmp_path.glob(".claude.json.*.tmp"))
    assert len(tmp_files) == 0


def test_load_missing_returns_empty():
    """load_claude_json returns empty dict for missing file."""
    with patch("arasul_tui.core.claude_json.CLAUDE_JSON", Path("/nonexistent/.claude.json")):
        assert load_claude_json() == {}


def test_load_invalid_json(tmp_path, monkeypatch):
    """load_claude_json returns empty dict for invalid JSON."""
    target = tmp_path / ".claude.json"
    target.write_text("not json{{{")
    monkeypatch.setattr("arasul_tui.core.claude_json.CLAUDE_JSON", target)
    assert load_claude_json() == {}


def test_roundtrip(tmp_path, monkeypatch):
    """Data survives a save/load roundtrip."""
    target = tmp_path / ".claude.json"
    monkeypatch.setattr("arasul_tui.core.claude_json.CLAUDE_JSON", target)
    data = {"mcpServers": {"playwright": {"command": "npx", "args": ["-y"]}}}
    save_claude_json(data)
    loaded = load_claude_json()
    assert loaded == data
