"""Tests for security commands and core security functions.

Strategy: Command handlers are tested through their public API (cmd_keys, etc.)
with mocked system calls. Core functions test real behavior where possible
(e.g., tmp_path for n8n .env file parsing).
"""

from __future__ import annotations

from unittest.mock import patch

from arasul_tui.commands.security import cmd_keys, cmd_logins, cmd_security
from arasul_tui.core.security import AuditItem, SSHKey, list_ssh_keys, recent_logins, security_audit
from arasul_tui.core.state import TuiState


def test_list_ssh_keys_no_ssh_dir():
    """Returns empty list when ~/.ssh doesn't exist."""
    with patch("arasul_tui.core.security.Path") as MockPath:
        mock_home = MockPath.home.return_value
        mock_ssh = mock_home.__truediv__.return_value
        mock_ssh.exists.return_value = False
        keys = list_ssh_keys()
    assert keys == []


def test_recent_logins_fallback():
    """Falls back gracefully when system commands fail."""
    with patch("arasul_tui.core.security.run_cmd", return_value="Error: command not found"):
        result = recent_logins()
    assert len(result) >= 1


def test_security_audit_returns_items():
    """security_audit returns AuditItem list with valid statuses."""
    with patch("arasul_tui.core.security.run_cmd", return_value=""), patch("arasul_tui.core.security.Path") as MockPath:
        mock_home = MockPath.home.return_value
        mock_ssh = mock_home.__truediv__.return_value
        mock_ssh.exists.return_value = False
        mock_conf = MockPath.return_value
        mock_conf.exists.return_value = False
        items = security_audit()
    assert isinstance(items, list)
    for item in items:
        assert isinstance(item, AuditItem)
        assert item.status in ("ok", "warn", "fail")


def test_n8n_security_audit_not_installed(tmp_path):
    """n8n audit returns empty list when n8n directory doesn't exist."""
    from arasul_tui.core.security import _n8n_security_audit
    from tests.conftest import make_platform, mock_platform

    p = make_platform(storage_mount=tmp_path / "nonexistent")
    with mock_platform(p):
        items = _n8n_security_audit()
    assert items == []


def test_cmd_keys_no_keys(state: TuiState):
    """Command succeeds with empty key list."""
    with patch("arasul_tui.commands.security.list_ssh_keys", return_value=[]):
        result = cmd_keys(state, [])
    assert result.ok is True


def test_cmd_keys_with_keys(state: TuiState):
    """Command succeeds when keys are found."""
    keys = [SSHKey(type="ssh-ed25519", bits="256", fingerprint="SHA256:x", comment="me@host", path="/home/.ssh/id")]
    with patch("arasul_tui.commands.security.list_ssh_keys", return_value=keys):
        result = cmd_keys(state, [])
    assert result.ok is True


def test_cmd_logins(state: TuiState):
    """Login history command succeeds."""
    with patch("arasul_tui.commands.security.recent_logins", return_value=["user1 tty1 2024-01-01"]):
        result = cmd_logins(state, [])
    assert result.ok is True


def test_cmd_security(state: TuiState):
    """Security audit command succeeds."""
    items = [AuditItem(label="Test", detail="OK", status="ok")]
    with patch("arasul_tui.commands.security.security_audit", return_value=items):
        result = cmd_security(state, [])
    assert result.ok is True


def test_n8n_security_audit_with_env(tmp_path):
    """n8n audit checks encryption key strength from .env file."""
    from arasul_tui.core.security import _n8n_security_audit

    n8n_dir = tmp_path / "n8n"
    n8n_dir.mkdir()
    env_file = n8n_dir / ".env"
    env_file.write_text("N8N_ENCRYPTION_KEY=a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2\n")
    env_file.chmod(0o600)

    mock_plat = type("Platform", (), {"storage": type("Storage", (), {"mount": tmp_path})()})()
    with (
        patch("arasul_tui.core.platform.get_platform", return_value=mock_plat),
        patch("arasul_tui.core.security.run_cmd", return_value=""),
    ):
        items = _n8n_security_audit()

    labels = [i.label for i in items]
    assert any("encryption" in lbl for lbl in labels)
