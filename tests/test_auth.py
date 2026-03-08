from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from arasul_tui.core.auth import (
    TOKEN_PREFIX,
    _has_account,
    _has_token,
    _read_token,
    _write_account,
    _write_token,
    get_auth_env,
    is_claude_configured,
    save_claude_auth,
)


def _auth_patches(tmp_path: Path):
    """Return a context manager that patches all auth file paths."""
    profile = tmp_path / ".profile"
    bashrc = tmp_path / ".bashrc"
    profile.touch()
    bashrc.touch()
    return (
        patch("arasul_tui.core.auth.PROFILE", profile),
        patch("arasul_tui.core.auth.BASHRC", bashrc),
        patch("arasul_tui.core.auth._TOKEN_FILES", [profile, bashrc]),
    )


def test_read_token_no_files(tmp_path: Path):
    profile = tmp_path / ".profile_missing"
    bashrc = tmp_path / ".bashrc_missing"
    with (
        patch("arasul_tui.core.auth.PROFILE", profile),
        patch("arasul_tui.core.auth.BASHRC", bashrc),
        patch("arasul_tui.core.auth._TOKEN_FILES", [profile, bashrc]),
    ):
        assert _read_token() is None


def test_write_and_read_token(tmp_path: Path):
    p1, p2, p3 = _auth_patches(tmp_path)
    token = f"{TOKEN_PREFIX}test-token-12345"
    with p1, p2, p3:
        _write_token(token)
        assert _read_token() == token
        assert _has_token() is True


def test_write_token_overwrites(tmp_path: Path):
    p1, p2, p3 = _auth_patches(tmp_path)
    old_token = f"{TOKEN_PREFIX}old-token"
    new_token = f"{TOKEN_PREFIX}new-token"
    with p1, p2, p3:
        _write_token(old_token)
        _write_token(new_token)
        assert _read_token() == new_token
        # Ensure only one export line exists
        profile = tmp_path / ".profile"
        content = profile.read_text()
        assert content.count("CLAUDE_CODE_OAUTH_TOKEN") == 1


def test_has_account_no_file(tmp_path: Path):
    claude_json = tmp_path / ".claude.json"
    with patch("arasul_tui.core.claude_json.CLAUDE_JSON", claude_json):
        assert _has_account() is False


def test_has_account_empty_json(tmp_path: Path):
    claude_json = tmp_path / ".claude.json"
    claude_json.write_text("{}", encoding="utf-8")
    with patch("arasul_tui.core.claude_json.CLAUDE_JSON", claude_json):
        assert _has_account() is False


def test_has_account_valid(tmp_path: Path):
    claude_json = tmp_path / ".claude.json"
    claude_json.write_text(
        json.dumps({"oauthAccount": {"accountUuid": "abc-123", "emailAddress": "test@example.com"}}),
        encoding="utf-8",
    )
    with patch("arasul_tui.core.claude_json.CLAUDE_JSON", claude_json):
        assert _has_account() is True


def test_write_account(tmp_path: Path):
    claude_json = tmp_path / ".claude.json"
    with patch("arasul_tui.core.claude_json.CLAUDE_JSON", claude_json):
        _write_account("uuid-123", "test@example.com")
        data = json.loads(claude_json.read_text())
        assert data["oauthAccount"]["accountUuid"] == "uuid-123"
        assert data["oauthAccount"]["emailAddress"] == "test@example.com"
        assert data["hasCompletedOnboarding"] is True


def test_is_claude_configured(tmp_path: Path):
    p1, p2, p3 = _auth_patches(tmp_path)
    claude_json = tmp_path / ".claude.json"

    with p1, p2, p3, patch("arasul_tui.core.claude_json.CLAUDE_JSON", claude_json):
        assert is_claude_configured() is False

        token = f"{TOKEN_PREFIX}full-test-token"
        save_claude_auth(token, "uuid-456", "user@example.com")
        assert is_claude_configured() is True


def test_get_auth_env(tmp_path: Path):
    p1, p2, p3 = _auth_patches(tmp_path)

    with p1, p2, p3:
        assert get_auth_env() == {}

        token = f"{TOKEN_PREFIX}env-test-token"
        _write_token(token)
        env = get_auth_env()
        assert env["CLAUDE_CODE_OAUTH_TOKEN"] == token


def test_has_account_corrupt_json(tmp_path: Path):
    claude_json = tmp_path / ".claude.json"
    claude_json.write_text("not valid json", encoding="utf-8")
    with patch("arasul_tui.core.claude_json.CLAUDE_JSON", claude_json):
        assert _has_account() is False
