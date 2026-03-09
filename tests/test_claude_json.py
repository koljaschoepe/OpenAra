from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from arasul_tui.core.claude_json import load_claude_json, save_claude_json, update_claude_json


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


def test_update_creates_file(tmp_path: Path):
    claude_json = tmp_path / ".claude.json"
    with patch("arasul_tui.core.claude_json.CLAUDE_JSON", claude_json):
        update_claude_json(lambda d: d.update({"created": True}))
    data = json.loads(claude_json.read_text(encoding="utf-8"))
    assert data == {"created": True}


def test_update_merges_existing(tmp_path: Path):
    claude_json = tmp_path / ".claude.json"
    claude_json.write_text('{"existing": 1}', encoding="utf-8")
    with patch("arasul_tui.core.claude_json.CLAUDE_JSON", claude_json):
        update_claude_json(lambda d: d.update({"new_key": 2}))
    data = json.loads(claude_json.read_text(encoding="utf-8"))
    assert data == {"existing": 1, "new_key": 2}


def test_update_from_corrupt_file(tmp_path: Path):
    claude_json = tmp_path / ".claude.json"
    claude_json.write_text("not json!", encoding="utf-8")
    with patch("arasul_tui.core.claude_json.CLAUDE_JSON", claude_json):
        update_claude_json(lambda d: d.update({"recovered": True}))
    data = json.loads(claude_json.read_text(encoding="utf-8"))
    assert data == {"recovered": True}
