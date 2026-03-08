from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from arasul_tui.core.claude_json import load_claude_json, save_claude_json


def test_load_no_file(tmp_path: Path):
    claude_json = tmp_path / ".claude.json"
    with patch("arasul_tui.core.claude_json.CLAUDE_JSON", claude_json):
        assert load_claude_json() == {}


def test_load_valid_json(tmp_path: Path):
    claude_json = tmp_path / ".claude.json"
    claude_json.write_text('{"key": "value"}', encoding="utf-8")
    with patch("arasul_tui.core.claude_json.CLAUDE_JSON", claude_json):
        assert load_claude_json() == {"key": "value"}


def test_load_corrupt_json(tmp_path: Path):
    claude_json = tmp_path / ".claude.json"
    claude_json.write_text("not json", encoding="utf-8")
    with patch("arasul_tui.core.claude_json.CLAUDE_JSON", claude_json):
        assert load_claude_json() == {}


def test_save_creates_file(tmp_path: Path):
    claude_json = tmp_path / ".claude.json"
    with patch("arasul_tui.core.claude_json.CLAUDE_JSON", claude_json):
        save_claude_json({"hello": "world"})
    data = json.loads(claude_json.read_text(encoding="utf-8"))
    assert data == {"hello": "world"}


def test_save_overwrites(tmp_path: Path):
    claude_json = tmp_path / ".claude.json"
    claude_json.write_text('{"old": true}', encoding="utf-8")
    with patch("arasul_tui.core.claude_json.CLAUDE_JSON", claude_json):
        save_claude_json({"new": True})
    data = json.loads(claude_json.read_text(encoding="utf-8"))
    assert data == {"new": True}
    assert "old" not in data


def test_save_trailing_newline(tmp_path: Path):
    claude_json = tmp_path / ".claude.json"
    with patch("arasul_tui.core.claude_json.CLAUDE_JSON", claude_json):
        save_claude_json({})
    assert claude_json.read_text(encoding="utf-8").endswith("\n")
