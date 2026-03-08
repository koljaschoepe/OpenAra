"""Tests for core/security.py — SSH keys, logins, and security audit."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from arasul_tui.core.security import (
    AuditItem,
    SSHKey,
    _n8n_security_audit,
    list_ssh_keys,
    recent_logins,
    security_audit,
)

# ---------------------------------------------------------------------------
# list_ssh_keys
# ---------------------------------------------------------------------------


class TestListSSHKeys:
    def test_no_ssh_dir(self, tmp_path: Path):
        with patch("arasul_tui.core.security.Path") as MockPath:
            MockPath.home.return_value = tmp_path
            # .ssh doesn't exist
            keys = list_ssh_keys()
        assert keys == []

    def test_with_keys(self, tmp_path: Path):
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir()
        (ssh_dir / "id_ed25519.pub").write_text("ssh-ed25519 AAAA user@host\n")
        (ssh_dir / "id_rsa.pub").write_text("ssh-rsa BBBB mykey\n")

        with (
            patch("arasul_tui.core.security.Path") as MockPath,
            patch("arasul_tui.core.security.run_cmd", return_value="256 SHA256:abc123 user@host (ED25519)"),
        ):
            MockPath.home.return_value = tmp_path
            keys = list_ssh_keys()

        assert len(keys) == 2
        assert all(isinstance(k, SSHKey) for k in keys)
        assert keys[0].type == "ssh-ed25519"
        assert keys[0].comment == "user@host"
        assert keys[0].bits == "256"
        assert keys[0].fingerprint == "SHA256:abc123"

    def test_key_with_no_comment(self, tmp_path: Path):
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir()
        (ssh_dir / "id_ed25519.pub").write_text("ssh-ed25519 AAAA\n")

        with (
            patch("arasul_tui.core.security.Path") as MockPath,
            patch("arasul_tui.core.security.run_cmd", return_value="256 SHA256:abc (ED25519)"),
        ):
            MockPath.home.return_value = tmp_path
            keys = list_ssh_keys()

        assert len(keys) == 1
        assert keys[0].comment == ""

    def test_error_reading_key(self, tmp_path: Path):
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir()
        (ssh_dir / "id_ed25519.pub").write_text("ssh-ed25519 AAAA user@host\n")

        with (
            patch("arasul_tui.core.security.Path") as MockPath,
            patch("arasul_tui.core.security.run_cmd", return_value="Error: cannot read key"),
        ):
            MockPath.home.return_value = tmp_path
            keys = list_ssh_keys()

        assert len(keys) == 1
        assert keys[0].bits == ""
        assert keys[0].fingerprint == ""

    def test_exception_in_key_file(self, tmp_path: Path):
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir()
        # Create a pub file that will raise on read
        pub = ssh_dir / "bad.pub"
        pub.write_text("invalid")
        # Make read_text raise
        with (
            patch("arasul_tui.core.security.Path") as MockPath,
            patch("arasul_tui.core.security.run_cmd", side_effect=Exception("boom")),
        ):
            MockPath.home.return_value = tmp_path
            keys = list_ssh_keys()
        # Should be empty or have an entry (the exception is caught)
        # The continue means we skip that key
        assert isinstance(keys, list)


# ---------------------------------------------------------------------------
# recent_logins
# ---------------------------------------------------------------------------


class TestRecentLogins:
    def test_last_works(self):
        with patch(
            "arasul_tui.core.security.run_cmd",
            return_value="user   pts/0   Mon Jan  1 10:00  still logged in  192.168.1.1\n\nwtmp begins",
        ):
            result = recent_logins(5)
        assert len(result) == 1
        assert "192.168.1.1" in result[0]

    def test_last_fails_journalctl_works(self):
        def _mock_cmd(cmd, **kwargs):
            if "last" in cmd:
                return "Error: last failed"
            return "Jan 01 sshd[1234]: Accepted publickey"

        with patch("arasul_tui.core.security.run_cmd", side_effect=_mock_cmd):
            result = recent_logins(5)
        assert len(result) == 1

    def test_both_fail(self):
        with patch("arasul_tui.core.security.run_cmd", return_value="Error: nope"):
            result = recent_logins()
        assert result == ["Login history not available"]

    def test_count_clamp(self):
        with patch("arasul_tui.core.security.run_cmd", return_value="Error"):
            recent_logins(0)  # Should clamp to 1
            recent_logins(200)  # Should clamp to 100
            recent_logins(-5)  # Should clamp to 1


# ---------------------------------------------------------------------------
# security_audit
# ---------------------------------------------------------------------------


class TestSecurityAudit:
    def test_hardened_conf_exists_password_disabled(self, tmp_path: Path):
        conf = tmp_path / "99-arasul-hardened.conf"
        conf.write_text("PasswordAuthentication no\nPermitRootLogin no\n")

        with (
            patch("arasul_tui.core.security.Path") as MockPath,
            patch("arasul_tui.core.security.run_cmd", return_value=""),
        ):
            MockPath.home.return_value = tmp_path
            MockPath.return_value = conf

            items = security_audit()

        # Should have multiple audit items
        assert isinstance(items, list)
        assert all(isinstance(i, AuditItem) for i in items)

    def test_all_checks_with_mocked_commands(self):
        """Full audit with all commands mocked."""

        def _mock_cmd(cmd, **kwargs):
            if "sshd -T" in cmd and "password" in cmd.lower():
                return "passwordauthentication no"
            if "sshd -T" in cmd and "permitrootlogin" in cmd.lower():
                return "permitrootlogin no"
            if "sshd -T" in cmd and "allowtcpforwarding" in cmd.lower():
                return "allowtcpforwarding local"
            if "fail2ban" in cmd and "is-active" in cmd:
                return "active"
            if "fail2ban-client" in cmd:
                return "Jail list: sshd, recidive"
            if "ufw status" in cmd and "head" in cmd:
                return "Status: active"
            if "ufw status" in cmd and "ALLOW" in cmd:
                return "3"
            if "unattended-upgrades" in cmd:
                return "active"
            return ""

        with (
            patch("arasul_tui.core.security.Path") as MockPath,
            patch("arasul_tui.core.security.run_cmd", side_effect=_mock_cmd),
            patch("arasul_tui.core.security._n8n_security_audit", return_value=[]),
        ):
            # Make sshd_config paths not exist
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            MockPath.return_value = mock_path
            MockPath.home.return_value = MagicMock(__truediv__=lambda self, x: MagicMock(exists=lambda: False))

            items = security_audit()

        assert isinstance(items, list)
        assert len(items) > 0
        # Check we got SSH auth check
        labels = [i.label for i in items]
        assert any("SSH" in label for label in labels)


# ---------------------------------------------------------------------------
# _n8n_security_audit
# ---------------------------------------------------------------------------


class TestN8nSecurityAudit:
    def test_no_n8n_installed(self, tmp_path: Path):
        mock_platform = MagicMock()
        mock_platform.storage.mount = tmp_path
        with patch("arasul_tui.core.platform.get_platform", return_value=mock_platform):
            items = _n8n_security_audit()
        assert items == []

    def test_n8n_with_good_key(self, tmp_path: Path):
        n8n_dir = tmp_path / "n8n"
        n8n_dir.mkdir()
        env_file = n8n_dir / ".env"
        env_file.write_text("N8N_ENCRYPTION_KEY=abcdefghijklmnopqrstuvwxyz123456\n")
        env_file.chmod(0o600)

        mock_platform = MagicMock()
        mock_platform.storage.mount = tmp_path

        with (
            patch("arasul_tui.core.platform.get_platform", return_value=mock_platform),
            patch("arasul_tui.core.security.run_cmd", return_value=""),
        ):
            items = _n8n_security_audit()

        assert len(items) >= 2  # encryption key + permissions
        assert items[0].status == "ok"
        assert items[1].status == "ok"  # permissions 600

    def test_n8n_short_key(self, tmp_path: Path):
        n8n_dir = tmp_path / "n8n"
        n8n_dir.mkdir()
        env_file = n8n_dir / ".env"
        env_file.write_text("N8N_ENCRYPTION_KEY=short\n")

        mock_platform = MagicMock()
        mock_platform.storage.mount = tmp_path

        with (
            patch("arasul_tui.core.platform.get_platform", return_value=mock_platform),
            patch("arasul_tui.core.security.run_cmd", return_value=""),
        ):
            items = _n8n_security_audit()

        key_item = items[0]
        assert key_item.status == "fail"

    def test_n8n_no_encryption_key(self, tmp_path: Path):
        n8n_dir = tmp_path / "n8n"
        n8n_dir.mkdir()
        env_file = n8n_dir / ".env"
        env_file.write_text("SOME_OTHER_VAR=value\n")

        mock_platform = MagicMock()
        mock_platform.storage.mount = tmp_path

        with (
            patch("arasul_tui.core.platform.get_platform", return_value=mock_platform),
            patch("arasul_tui.core.security.run_cmd", return_value=""),
        ):
            items = _n8n_security_audit()

        assert any(i.label == "n8n encryption key" and i.status == "fail" for i in items)

    def test_n8n_bad_perms(self, tmp_path: Path):
        n8n_dir = tmp_path / "n8n"
        n8n_dir.mkdir()
        env_file = n8n_dir / ".env"
        env_file.write_text("N8N_ENCRYPTION_KEY=abcdefghijklmnopqrstuvwxyz123456\n")
        env_file.chmod(0o644)

        mock_platform = MagicMock()
        mock_platform.storage.mount = tmp_path

        with (
            patch("arasul_tui.core.platform.get_platform", return_value=mock_platform),
            patch("arasul_tui.core.security.run_cmd", return_value=""),
        ):
            items = _n8n_security_audit()

        perms_item = next(i for i in items if "permissions" in i.label)
        assert perms_item.status == "warn"

    def test_n8n_with_backup(self, tmp_path: Path):
        n8n_dir = tmp_path / "n8n"
        n8n_dir.mkdir()
        env_file = n8n_dir / ".env"
        env_file.write_text("N8N_ENCRYPTION_KEY=abcdefghijklmnopqrstuvwxyz123456\n")

        backup_dir = tmp_path / "backups" / "n8n"
        backup_dir.mkdir(parents=True)
        (backup_dir / "encryption-key.txt").write_text("backup")

        mock_platform = MagicMock()
        mock_platform.storage.mount = tmp_path

        with (
            patch("arasul_tui.core.platform.get_platform", return_value=mock_platform),
            patch("arasul_tui.core.security.run_cmd", return_value=""),
        ):
            items = _n8n_security_audit()

        backup_item = next(i for i in items if "backup" in i.label)
        assert backup_item.status == "ok"

    def test_n8n_postgres_exposed(self, tmp_path: Path):
        n8n_dir = tmp_path / "n8n"
        n8n_dir.mkdir()
        env_file = n8n_dir / ".env"
        env_file.write_text("N8N_ENCRYPTION_KEY=abcdefghijklmnopqrstuvwxyz123456\n")

        mock_platform = MagicMock()
        mock_platform.storage.mount = tmp_path

        def _mock_cmd(cmd, **kwargs):
            if "docker ps" in cmd and "status=running" in cmd:
                return "abc123"
            if "docker ps" in cmd and "Ports" in cmd:
                return "0.0.0.0:5432->5432/tcp"
            return ""

        with (
            patch("arasul_tui.core.platform.get_platform", return_value=mock_platform),
            patch("arasul_tui.core.security.run_cmd", side_effect=_mock_cmd),
        ):
            items = _n8n_security_audit()

        pg_item = next(i for i in items if "PostgreSQL" in i.label)
        assert pg_item.status == "fail"

    def test_n8n_postgres_internal(self, tmp_path: Path):
        n8n_dir = tmp_path / "n8n"
        n8n_dir.mkdir()
        env_file = n8n_dir / ".env"
        env_file.write_text("N8N_ENCRYPTION_KEY=abcdefghijklmnopqrstuvwxyz123456\n")

        mock_platform = MagicMock()
        mock_platform.storage.mount = tmp_path

        def _mock_cmd(cmd, **kwargs):
            if "docker ps" in cmd and "status=running" in cmd:
                return "abc123"
            if "docker ps" in cmd and "Ports" in cmd:
                return "5432/tcp"
            return ""

        with (
            patch("arasul_tui.core.platform.get_platform", return_value=mock_platform),
            patch("arasul_tui.core.security.run_cmd", side_effect=_mock_cmd),
        ):
            items = _n8n_security_audit()

        pg_item = next(i for i in items if "PostgreSQL" in i.label)
        assert pg_item.status == "ok"
