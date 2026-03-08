#!/usr/bin/env bash
# =============================================================================
# 03 — SSH Hardening
# Key-only auth, disable root login, fail2ban with recidive jail
# IMPORTANT: SSH key must be copied first!
# =============================================================================
set -euo pipefail

# shellcheck source=../lib/common.sh
source "$(dirname "$0")/../lib/common.sh"

# Defaults for standalone execution
REAL_USER="${REAL_USER:-$(logname 2>/dev/null || echo "${SUDO_USER:-$USER}")}"
REAL_HOME="${REAL_HOME:-$(getent passwd "$REAL_USER" 2>/dev/null | cut -d: -f6 || echo "$HOME")}"
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
    cat > "$SSHD_DROPIN" << 'EOF'
# Arasul — SSH Hardening
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
UsePAM yes
X11Forwarding no
MaxAuthTries 3
LoginGraceTime 20
ClientAliveInterval 60
ClientAliveCountMax 3
AllowAgentForwarding no
AllowTcpForwarding local
PrintLastLog yes

# Strong crypto only
Ciphers chacha20-poly1305@openssh.com,aes256-gcm@openssh.com,aes128-gcm@openssh.com
MACs hmac-sha2-512-etm@openssh.com,hmac-sha2-256-etm@openssh.com
KexAlgorithms curve25519-sha256,curve25519-sha256@libssh.org,diffie-hellman-group16-sha512
HostKeyAlgorithms ssh-ed25519,rsa-sha2-512,rsa-sha2-256
EOF

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

    cat > /etc/fail2ban/jail.local << 'EOF'
[DEFAULT]
bantime  = 3600
findtime = 600
maxretry = 3

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
