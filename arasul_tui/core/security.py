from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path

from arasul_tui.core.shell import run_cmd


@dataclass
class SSHKey:
    type: str
    bits: str
    fingerprint: str
    comment: str
    path: str


@dataclass
class AuditItem:
    label: str
    detail: str
    status: str  # "ok", "warn", "fail"


def list_ssh_keys() -> list[SSHKey]:
    """List SSH keys in ~/.ssh/."""
    keys: list[SSHKey] = []
    ssh_dir = Path.home() / ".ssh"
    if not ssh_dir.exists():
        return keys

    for pub in sorted(ssh_dir.glob("*.pub")):
        try:
            content = pub.read_text(encoding="utf-8").strip()
            parts = content.split(None, 2)
            key_type = parts[0] if parts else "unknown"
            comment = parts[2] if len(parts) > 2 else ""

            fp_out = run_cmd(f"ssh-keygen -lf {shlex.quote(str(pub))}")
            bits = ""
            fingerprint = ""
            if fp_out and not fp_out.startswith("Error"):
                fp_parts = fp_out.split()
                bits = fp_parts[0] if fp_parts else ""
                fingerprint = fp_parts[1] if len(fp_parts) > 1 else ""

            keys.append(
                SSHKey(
                    type=key_type,
                    bits=bits,
                    fingerprint=fingerprint,
                    comment=comment,
                    path=str(pub),
                )
            )
        except Exception:
            continue

    return keys


def recent_logins(count: int = 10) -> list[str]:
    """Return recent SSH login lines from last/journalctl."""
    n = max(1, min(count, 100))
    out = run_cmd(f"last -n {n} -a 2>/dev/null", timeout=5)
    if out and not out.startswith("Error"):
        lines = [line for line in out.splitlines() if line.strip() and not line.startswith("wtmp")]
        return lines[:n]

    out = run_cmd(f"journalctl -u sshd -n {n} --no-pager 2>/dev/null", timeout=5)
    if out and not out.startswith("Error"):
        return out.splitlines()[:n]

    return ["Login history not available"]


def _has_passwordless_sudo() -> bool:
    """Check if current user can run sudo without password prompt."""
    result = run_cmd("sudo -n true 2>/dev/null", timeout=2)
    return result is not None and not result.startswith("Error")


def security_audit() -> list[AuditItem]:
    """Run security checks and return audit items."""
    items: list[AuditItem] = []
    can_sudo = _has_passwordless_sudo()

    # SSH key-only auth
    sshd_conf = Path("/etc/ssh/sshd_config.d/99-arasul-hardened.conf")
    if not sshd_conf.exists():
        sshd_conf = Path("/etc/ssh/sshd_config.d/99-jetson-hardened.conf")
    try:
        content = sshd_conf.read_text(encoding="utf-8", errors="replace") if sshd_conf.exists() else ""
    except OSError:
        content = ""
    if content:
        if "PasswordAuthentication no" in content:
            items.append(AuditItem("SSH key-only auth", "Password login disabled", "ok"))
        else:
            items.append(AuditItem("SSH key-only auth", "Password login may be enabled", "warn"))
    else:
        passwd_auth = run_cmd("sshd -T 2>/dev/null | grep -i '^passwordauthentication'", timeout=3)
        if passwd_auth and not passwd_auth.startswith("Error") and "passwordauthentication no" in passwd_auth.lower():
            items.append(AuditItem("SSH key-only auth", "Password login disabled", "ok"))
        elif not passwd_auth or passwd_auth.startswith("Error"):
            items.append(AuditItem("SSH key-only auth", "Cannot check (sshd -T failed)", "warn"))
        else:
            items.append(AuditItem("SSH key-only auth", "Password login enabled", "fail"))

    # fail2ban
    f2b = run_cmd("systemctl is-active fail2ban 2>/dev/null")
    if f2b == "active":
        if can_sudo:
            jails = run_cmd("sudo fail2ban-client status 2>/dev/null | grep 'Jail list'", timeout=5)
            detail = jails.split(":", 1)[-1].strip() if ":" in jails else "active"
        else:
            detail = "active (run as root for details)"
        items.append(AuditItem("fail2ban active", detail, "ok"))
    else:
        items.append(AuditItem("fail2ban", "Not running", "fail"))

    # UFW firewall
    if can_sudo:
        ufw = run_cmd("sudo ufw status 2>/dev/null | head -1", timeout=5)
        if "status: active" in ufw.lower():
            rules = run_cmd("sudo ufw status 2>/dev/null | grep -c ALLOW", timeout=5)
            items.append(AuditItem("UFW firewall", f"{rules} rules active" if rules.isdigit() else "Active", "ok"))
        else:
            items.append(AuditItem("UFW firewall", "Inactive", "fail"))
    else:
        items.append(AuditItem("UFW firewall", "Cannot check (no sudo)", "warn"))

    # Root login
    root_check = run_cmd("sshd -T 2>/dev/null | grep -i permitrootlogin", timeout=3)
    if root_check and not root_check.startswith("Error"):
        if "no" in root_check.lower():
            items.append(AuditItem("Root login disabled", "PermitRootLogin no", "ok"))
        elif "without-password" in root_check.lower() or "prohibit-password" in root_check.lower():
            items.append(AuditItem("Root login restricted", "Key-only root access", "warn"))
        else:
            items.append(AuditItem("Root login", "May be enabled", "fail"))
    else:
        items.append(AuditItem("Root login", "Cannot check (sshd -T failed)", "warn"))

    # SSH TCP forwarding
    tcp_fwd = run_cmd("sshd -T 2>/dev/null | grep -i allowtcpforwarding", timeout=3)
    if tcp_fwd and not tcp_fwd.startswith("Error"):
        val = tcp_fwd.strip().split()[-1].lower() if tcp_fwd.strip() else ""
        if val in ("no", "local"):
            items.append(AuditItem("TCP forwarding", val, "ok"))
        elif val == "yes":
            items.append(AuditItem("TCP forwarding", "Unrestricted (consider 'local')", "warn"))

    # SSH directory and authorized_keys permissions
    ssh_dir = Path.home() / ".ssh"
    if ssh_dir.exists():
        try:
            ssh_mode = oct(ssh_dir.stat().st_mode)[-3:]
        except OSError:
            ssh_mode = None
        if ssh_mode == "700":
            items.append(AuditItem("~/.ssh permissions", "700", "ok"))
        elif ssh_mode:
            items.append(AuditItem("~/.ssh permissions", f"{ssh_mode} (should be 700)", "warn"))

        auth_keys = ssh_dir / "authorized_keys"
        if auth_keys.exists():
            try:
                ak_mode = oct(auth_keys.stat().st_mode)[-3:]
            except OSError:
                ak_mode = None
            if ak_mode == "600":
                items.append(AuditItem("authorized_keys perms", ak_mode, "ok"))
            elif ak_mode == "644":
                items.append(AuditItem("authorized_keys perms", f"{ak_mode} (should be 600)", "warn"))
            elif ak_mode:
                items.append(AuditItem("authorized_keys perms", f"{ak_mode} (should be 600)", "fail"))

    # SSH key algorithm
    if (ssh_dir / "id_ed25519.pub").exists():
        items.append(AuditItem("SSH key algorithm", "Ed25519", "ok"))
    elif (ssh_dir / "id_rsa.pub").exists():
        items.append(AuditItem("SSH key algorithm", "RSA (Ed25519 recommended)", "warn"))
    else:
        items.append(AuditItem("SSH key algorithm", "No key found", "warn"))

    # Unattended upgrades
    ua = run_cmd("systemctl is-active unattended-upgrades 2>/dev/null")
    if ua == "active":
        items.append(AuditItem("Auto security updates", "unattended-upgrades active", "ok"))
    else:
        items.append(AuditItem("Auto security updates", "Not configured", "warn"))

    # n8n security checks (only if installed)
    items.extend(_n8n_security_audit())

    return items


def _n8n_security_audit() -> list[AuditItem]:
    """n8n-specific security checks."""
    from arasul_tui.core.platform import get_platform

    items: list[AuditItem] = []
    mount = get_platform().storage.mount
    n8n_env = mount / "n8n" / ".env"

    if not n8n_env.exists():
        return items  # n8n not installed, skip silently

    # Encryption key exists
    try:
        content = n8n_env.read_text(encoding="utf-8", errors="replace")
        if "N8N_ENCRYPTION_KEY=" in content:
            key_line = [ln for ln in content.splitlines() if ln.startswith("N8N_ENCRYPTION_KEY=")]
            key = key_line[0].split("=", 1)[1] if key_line else ""
            if len(key) >= 32:
                items.append(AuditItem("n8n encryption key", f"{len(key)} chars", "ok"))
            else:
                items.append(AuditItem("n8n encryption key", "Too short or missing", "fail"))
        else:
            items.append(AuditItem("n8n encryption key", "Not set", "fail"))
    except Exception:
        items.append(AuditItem("n8n encryption key", "Cannot read .env", "warn"))

    # .env file permissions
    try:
        mode = oct(n8n_env.stat().st_mode)[-3:]
        if mode == "600":
            items.append(AuditItem("n8n .env permissions", "600 (owner only)", "ok"))
        else:
            items.append(AuditItem("n8n .env permissions", f"{mode} (should be 600)", "warn"))
    except Exception:
        pass

    # Encryption key backup
    backup = mount / "backups" / "n8n" / "encryption-key.txt"
    if backup.exists():
        items.append(AuditItem("n8n key backup", str(backup), "ok"))
    else:
        items.append(AuditItem("n8n key backup", "No backup found", "warn"))

    # PostgreSQL not exposed
    n8n_running = run_cmd("docker ps --filter name=n8n --filter status=running -q 2>/dev/null", timeout=5)
    if n8n_running and not n8n_running.startswith("Error"):
        pg_ports = run_cmd("docker ps --filter name=postgres --format '{{.Ports}}' 2>/dev/null", timeout=5)
        if pg_ports and "0.0.0.0" in pg_ports:
            items.append(AuditItem("n8n PostgreSQL", "Exposed externally", "fail"))
        else:
            items.append(AuditItem("n8n PostgreSQL", "Internal only", "ok"))

    # UFW rule for 5678
    can_sudo = _has_passwordless_sudo()
    ufw_n8n = run_cmd("sudo ufw status 2>/dev/null | grep 5678", timeout=5) if can_sudo else ""
    if ufw_n8n and not ufw_n8n.startswith("Error"):
        if "/" in ufw_n8n and "Anywhere" not in ufw_n8n:
            items.append(AuditItem("n8n firewall", "LAN restricted", "ok"))
        else:
            items.append(AuditItem("n8n firewall", "Open to all", "warn"))

    return items
