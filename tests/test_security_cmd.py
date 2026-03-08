from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from arasul_tui.commands.security import cmd_keys, cmd_logins, cmd_security
from arasul_tui.core.platform import GpuInfo, Platform, StorageInfo
from arasul_tui.core.router import REGISTRY
from arasul_tui.core.security import AuditItem, SSHKey, list_ssh_keys, recent_logins, security_audit
from arasul_tui.core.state import TuiState


def _make_platform(storage_mount: Path = Path("/tmp/test")) -> Platform:
    return Platform(
        name="generic",
        model="Test",
        arch="aarch64",
        ram_mb=8192,
        gpu=GpuInfo(type="none", has_cuda=False, cuda_version=""),
        storage=StorageInfo(type="sd_only", mount=storage_mount, device=""),
        has_docker=False,
        has_nvidia_runtime=False,
    )


def test_ssh_key_dataclass():
    key = SSHKey(
        type="ssh-ed25519",
        bits="256",
        fingerprint="SHA256:abc",
        comment="user@host",
        path="/home/user/.ssh/id_ed25519.pub",
    )
    assert key.type == "ssh-ed25519"
    assert key.bits == "256"


def test_audit_item_dataclass():
    item = AuditItem(label="SSH key-only auth", detail="Password login disabled", status="ok")
    assert item.status == "ok"
    assert item.label == "SSH key-only auth"


def test_list_ssh_keys_no_ssh_dir():
    with patch("arasul_tui.core.security.Path") as MockPath:
        mock_home = MockPath.home.return_value
        mock_ssh = mock_home.__truediv__.return_value
        mock_ssh.exists.return_value = False
        keys = list_ssh_keys()
    assert keys == []


def test_recent_logins_fallback():
    """Falls back gracefully when commands fail."""
    with patch("arasul_tui.core.security.run_cmd", return_value="Error: command not found"):
        result = recent_logins()
    assert len(result) >= 1


def test_security_audit_returns_items():
    """security_audit returns AuditItem list."""
    with patch("arasul_tui.core.security.run_cmd", return_value=""), patch("arasul_tui.core.security.Path") as MockPath:
        mock_home = MockPath.home.return_value
        mock_ssh = mock_home.__truediv__.return_value
        mock_ssh.exists.return_value = False
        # Mock sshd config path
        mock_conf = MockPath.return_value
        mock_conf.exists.return_value = False
        items = security_audit()
    assert isinstance(items, list)
    for item in items:
        assert isinstance(item, AuditItem)
        assert item.status in ("ok", "warn", "fail")


def test_n8n_security_audit_not_installed(tmp_path):
    """n8n audit returns empty list when n8n is not installed."""
    from arasul_tui.core.security import _n8n_security_audit

    fake_platform = _make_platform(storage_mount=tmp_path / "nonexistent")
    with patch("arasul_tui.core.platform.get_platform", return_value=fake_platform):
        items = _n8n_security_audit()
    assert items == []


def _state() -> TuiState:
    return TuiState(registry=REGISTRY)


def test_cmd_keys_no_keys():
    with patch("arasul_tui.commands.security.list_ssh_keys", return_value=[]):
        result = cmd_keys(_state(), [])
    assert result.ok is True


def test_cmd_keys_with_keys():
    keys = [SSHKey(type="ssh-ed25519", bits="256", fingerprint="SHA256:x", comment="me@host", path="/home/.ssh/id")]
    with patch("arasul_tui.commands.security.list_ssh_keys", return_value=keys):
        result = cmd_keys(_state(), [])
    assert result.ok is True


def test_cmd_logins():
    with patch("arasul_tui.commands.security.recent_logins", return_value=["user1 tty1 2024-01-01"]):
        result = cmd_logins(_state(), [])
    assert result.ok is True


def test_cmd_security():
    items = [AuditItem(label="Test", detail="OK", status="ok")]
    with patch("arasul_tui.commands.security.security_audit", return_value=items):
        result = cmd_security(_state(), [])
    assert result.ok is True


def test_n8n_security_audit_with_env(tmp_path):
    """n8n audit checks encryption key from .env file."""
    from arasul_tui.core.security import _n8n_security_audit

    # Create n8n directory structure under tmp_path (simulated storage mount)
    n8n_dir = tmp_path / "n8n"
    n8n_dir.mkdir()
    env_file = n8n_dir / ".env"
    env_file.write_text("N8N_ENCRYPTION_KEY=a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2\n")
    env_file.chmod(0o600)

    mock_platform = type("Platform", (), {"storage": type("Storage", (), {"mount": tmp_path})()})()
    with (
        patch("arasul_tui.core.platform.get_platform", return_value=mock_platform),
        patch("arasul_tui.core.security.run_cmd", return_value=""),
    ):
        items = _n8n_security_audit()

    # Should have at least the encryption key check
    labels = [i.label for i in items]
    assert any("encryption" in lbl for lbl in labels)
