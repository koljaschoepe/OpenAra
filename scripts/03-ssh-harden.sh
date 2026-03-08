#!/usr/bin/env bash
# =============================================================================
# 03 — SSH Hardening
# Key-only auth, disable root login, fail2ban with recidive jail
# IMPORTANT: SSH key must be copied first!
# =============================================================================
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

# shellcheck source=../lib/common.sh
source "$(dirname "$0")/../lib/common.sh"

# Defaults for standalone execution
REAL_USER="${REAL_USER:-$(logname 2>/dev/null || echo "${SUDO_USER:-$USER}")}"
REAL_HOME="${REAL_HOME:-$(get_real_home)}"
DEVICE_HOSTNAME="${DEVICE_HOSTNAME:-$(hostname)}"

# ---------------------------------------------------------------------------
# Safety check: SSH keys present?
# ---------------------------------------------------------------------------
if [[ "${SKIP_SSH_HARDENING:-}" == "true" ]]; then
    warn "SSH hardening skipped (no SSH key found during pre-flight)"
    warn "Run setup again after copying your SSH key"
    exit 2
fi

AUTH_KEYS="${REAL_HOME}/.ssh/authorized_keys"
if [[ ! -f "$AUTH_KEYS" ]] || [[ ! -s "$AUTH_KEYS" ]]; then
    err "No SSH authorized_keys found for ${REAL_USER}!"
    err ""
    err "Copy your SSH key first:"
    err "  ssh-copy-id ${REAL_USER}@${DEVICE_HOSTNAME}.local"
    err ""
    err "SSH hardening skipped to prevent lockout"
    exit 2
fi

KEY_COUNT=$(wc -l < "$AUTH_KEYS")
log "${KEY_COUNT} SSH key(s) found in authorized_keys"

# ---------------------------------------------------------------------------
# Harden SSH daemon
# ---------------------------------------------------------------------------
SSHD_DROPIN="/etc/ssh/sshd_config.d/99-arasul-hardened.conf"
SSHD_LEGACY="/etc/ssh/sshd_config.d/99-jetson-hardened.conf"

# Rename old config if upgrading
if [[ -f "$SSHD_LEGACY" ]] && [[ ! -f "$SSHD_DROPIN" ]]; then
    mv "$SSHD_LEGACY" "$SSHD_DROPIN"
    log "Renamed SSH config: 99-jetson-hardened.conf → 99-arasul-hardened.conf"
fi

if [[ ! -f "$SSHD_DROPIN" ]]; then
    backup_config /etc/ssh/sshd_config
    # Build SSH hardening config dynamically for portability
    {
        echo "# Arasul — SSH Hardening"
        echo "PermitRootLogin no"
        echo "PasswordAuthentication no"
        # KbdInteractiveAuthentication replaces ChallengeResponseAuthentication in OpenSSH 8.7+
        # Older versions (e.g. Ubuntu 20.04) only know ChallengeResponseAuthentication
        if sshd -T 2>/dev/null | grep -qi kbdinteractiveauthentication; then
            echo "KbdInteractiveAuthentication no"
        else
            echo "ChallengeResponseAuthentication no"
        fi
        echo "UsePAM yes"
        echo "X11Forwarding no"
        echo "MaxAuthTries 3"
        echo "LoginGraceTime 20"
        echo "ClientAliveInterval 60"
        echo "ClientAliveCountMax 3"
        echo "AllowAgentForwarding no"
        echo "AllowTcpForwarding local"
        echo "PrintLastLog yes"
        echo ""
        echo "# Strong crypto only"
        echo "Ciphers chacha20-poly1305@openssh.com,aes256-gcm@openssh.com,aes128-gcm@openssh.com"
        echo "MACs hmac-sha2-512-etm@openssh.com,hmac-sha2-256-etm@openssh.com"
        echo "KexAlgorithms curve25519-sha256,curve25519-sha256@libssh.org,diffie-hellman-group16-sha512"
        echo "HostKeyAlgorithms ssh-ed25519,rsa-sha2-512,rsa-sha2-256"
    } > "$SSHD_DROPIN"

    if sshd -t 2>/dev/null; then
        systemctl restart sshd 2>/dev/null || systemctl restart ssh
        log "SSH hardened: password auth disabled, root login disabled"
    else
        err "SSH configuration invalid — reverting"
        rm -f "$SSHD_DROPIN"
        exit 1
    fi
else
    skip "SSH already hardened"
fi

# ---------------------------------------------------------------------------
# fail2ban with recidive jail
# ---------------------------------------------------------------------------
if ! dpkg -l fail2ban 2>/dev/null | grep -q "^ii"; then
    apt-get install -y -qq fail2ban

    backup_config /etc/fail2ban/jail.local
    cat > /etc/fail2ban/jail.local << 'EOF'
[DEFAULT]
bantime  = 3600
findtime = 600
maxretry = 3
ignoreip = 127.0.0.1/8 ::1 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16

[sshd]
enabled  = true
port     = ssh
logpath  = %(sshd_log)s
backend  = systemd
maxretry = 3

[recidive]
enabled  = true
logpath  = /var/log/fail2ban.log
banaction = %(banaction_allports)s
bantime  = 1w
findtime = 1d
maxretry = 5
EOF

    systemctl enable --now fail2ban
    log "fail2ban installed (3 attempts → 1h ban, repeat offenders → 1 week ban)"
else
    # Ensure recidive jail exists even if fail2ban was already installed
    if [[ -f /etc/fail2ban/jail.local ]] && ! grep -q "recidive" /etc/fail2ban/jail.local 2>/dev/null; then
        cat >> /etc/fail2ban/jail.local << 'EOF'

[recidive]
enabled  = true
logpath  = /var/log/fail2ban.log
banaction = %(banaction_allports)s
bantime  = 1w
findtime = 1d
maxretry = 5
EOF
        systemctl restart fail2ban
        log "Recidive jail added to fail2ban"
    else
        skip "fail2ban already installed"
    fi
fi

log "SSH hardening complete"
warn "Test SSH key login from your Mac before closing this session!"
