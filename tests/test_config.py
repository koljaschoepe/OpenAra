"""Tests for user config (display_name persistence)."""

from __future__ import annotations

import json

from arasul_tui.core.config import get_display_name, set_display_name


def test_get_display_name_missing(tmp_path, monkeypatch):
    """Returns empty string when config file doesn't exist."""
    monkeypatch.setattr("arasul_tui.core.config.CONFIG_FILE", tmp_path / "config.json")
    assert get_display_name() == ""


def test_set_and_get_display_name(tmp_path, monkeypatch):
    """Name survives a set/get roundtrip."""
    cfg = tmp_path / "config.json"
    monkeypatch.setattr("arasul_tui.core.config.CONFIG_FILE", cfg)
    monkeypatch.setattr("arasul_tui.core.config.CONFIG_DIR", tmp_path)
    set_display_name("Kolja")
    assert get_display_name() == "Kolja"


def test_set_preserves_other_keys(tmp_path, monkeypatch):
    """Setting display_name doesn't clobber other config keys."""
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"theme": "dark"}))
    monkeypatch.setattr("arasul_tui.core.config.CONFIG_FILE", cfg)
    monkeypatch.setattr("arasul_tui.core.config.CONFIG_DIR", tmp_path)
    set_display_name("Max")
    data = json.loads(cfg.read_text())
    assert data["display_name"] == "Max"
    assert data["theme"] == "dark"


def test_get_invalid_json(tmp_path, monkeypatch):
    """Returns empty string for corrupted config file."""
    cfg = tmp_path / "config.json"
    cfg.write_text("not json{{{")
    monkeypatch.setattr("arasul_tui.core.config.CONFIG_FILE", cfg)
    assert get_display_name() == ""
