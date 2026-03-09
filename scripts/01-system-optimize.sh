#!/usr/bin/env bash
# =============================================================================
# 01 — System Optimization
# Disable desktop GUI, stop unnecessary services, tune kernel, configure
# journald limits, OOM protection, and automatic security updates.
# =============================================================================
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

# shellcheck source=../lib/common.sh
source "$(dirname "$0")/../lib/common.sh"

# shellcheck source=../lib/detect.sh
source "$(dirname "$0")/../lib/detect.sh"

check_root

# Ensure log directory exists (used by health crons and setup scripts)
mkdir -p /var/log/arasul

# Defaults for standalone execution
REAL_USER="${REAL_USER:-$(logname 2>/dev/null || echo "${SUDO_USER:-$USER}")}"
REAL_HOME="${REAL_HOME:-$(get_real_home)}"
PLATFORM="${PLATFORM:-$(detect_platform)}"

# ---------------------------------------------------------------------------
# Disable desktop environment
# ---------------------------------------------------------------------------
if command -v systemctl &>/dev/null; then
    CURRENT_TARGET=$(systemctl get-default 2>/dev/null || echo "unknown")
    if [[ "$CURRENT_TARGET" == "graphical.target" ]]; then
        log "Switching to multi-user.target (headless)..."
        systemctl set-default multi-user.target
        systemctl stop gdm3 2>/dev/null || true
        systemctl disable gdm3 2>/dev/null || true
        log "Desktop disabled — ~800MB RAM saved"
    else
        skip "Already in headless mode"
    fi
else
    skip "systemd not available — skipping desktop disable"
fi

# ---------------------------------------------------------------------------
# Disable unnecessary services
# ---------------------------------------------------------------------------
DISABLE_SERVICES=(
    "bluetooth.service"
    "cups.service"
    "cups-browsed.service"
    "ModemManager.service"
    "colord.service"
    "whoopsie.service"
    "apport.service"
)

# Jetson-only: camera daemon
if [[ "$PLATFORM" == "jetson" ]]; then
    DISABLE_SERVICES+=("nvargus-daemon.service")
fi

for svc in "${DISABLE_SERVICES[@]}"; do
    if systemctl is-enabled "$svc" &>/dev/null; then
        systemctl disable --now "$svc" 2>/dev/null || true
        log "Disabled: $svc"
    fi
done

# wpa_supplicant: only disable if connected via Ethernet (WiFi disable = brick)
if systemctl is-enabled wpa_supplicant.service &>/dev/null; then
    if ip route show default | grep -qE "dev (eth|enp|eno|ens)"; then
        systemctl disable --now wpa_supplicant.service 2>/dev/null || true
        log "Disabled: wpa_supplicant.service (Ethernet connection detected)"
    else
        log "Skipping wpa_supplicant disable (WiFi connection detected)"
    fi
fi

# ---------------------------------------------------------------------------
# Remove desktop packages (~3GB disk space)
# ---------------------------------------------------------------------------
if dpkg -l | grep -q ubuntu-desktop 2>/dev/null; then
    log "Removing Ubuntu desktop packages (takes a few minutes)..."
    apt-get remove --purge -y \
        ubuntu-desktop \
        gdm3 \
        gnome-shell \
        gnome-terminal \
        nautilus \
        firefox \
        thunderbird \
        'libreoffice*' \
        2>/dev/null || true
    apt-get autoremove --purge -y 2>/dev/null || true
    apt-get clean

    # NetworkManager must survive
    apt-get install -y network-manager 2>/dev/null || true
    log "Desktop packages removed — ~3GB disk space freed"
elif dpkg -l | grep -q raspberrypi-ui-mods 2>/dev/null; then
    log "Removing Raspberry Pi desktop packages..."
    apt-get remove --purge -y \
        raspberrypi-ui-mods \
        lightdm \
        lxde-core \
        lxpanel \
        lxappearance \
        pcmanfm \
        rpd-wallpaper \
        'libreoffice*' \
        2>/dev/null || true
    apt-get autoremove --purge -y 2>/dev/null || true
    apt-get clean
    log "RPi desktop packages removed — ~800MB freed"
else
    skip "Desktop packages already removed (or headless install)"
fi

# ---------------------------------------------------------------------------
# System updates and base packages
# ---------------------------------------------------------------------------
log "Updating package lists..."
apt-get update -qq

BASE_PACKAGES=(
    curl wget htop tree jq unzip net-tools
    smartmontools lsof ca-certificates gnupg
    parted
)

# Only install nvme-cli if NVMe storage detected
if has_nvme 2>/dev/null; then
    BASE_PACKAGES+=(nvme-cli)
fi

log "Installing base packages..."
apt-get install -y -qq "${BASE_PACKAGES[@]}" 2>/dev/null

# ---------------------------------------------------------------------------
# Kernel parameter tuning
# ---------------------------------------------------------------------------
SYSCTL_FILE="/etc/sysctl.d/99-arasul-system.conf"
OLD_SYSCTL_FILE="/etc/sysctl.d/99-jetson-dev.conf"

# Backward compat: accept old name as already-done
if [[ -f "$OLD_SYSCTL_FILE" ]] && [[ ! -f "$SYSCTL_FILE" ]]; then
    mv "$OLD_SYSCTL_FILE" "$SYSCTL_FILE"
    log "Renamed ${OLD_SYSCTL_FILE} → ${SYSCTL_FILE}"
fi

SYSCTL_VERSION="2"  # Bump to force regeneration on upgrades

if [[ ! -f "$SYSCTL_FILE" ]] || ! grep -q "# version=$SYSCTL_VERSION" "$SYSCTL_FILE" 2>/dev/null; then
    [[ -f "$SYSCTL_FILE" ]] && backup_config "$SYSCTL_FILE"
    cat > "$SYSCTL_FILE" << 'EOF'
# Arasul Dev Server — Kernel Tuning
# version=2
vm.swappiness=10
vm.vfs_cache_pressure=50
vm.dirty_ratio=10
vm.min_free_kbytes=65536
fs.inotify.max_user_watches=524288
fs.inotify.max_user_instances=512
net.core.somaxconn=65535
net.core.rmem_max=16777216
net.core.wmem_max=16777216
fs.file-max=2097152

# Network hardening
net.ipv4.tcp_syncookies=1
net.ipv4.conf.all.rp_filter=1
net.ipv4.conf.default.rp_filter=1
net.ipv4.conf.all.accept_redirects=0
net.ipv4.conf.default.accept_redirects=0
net.ipv4.conf.all.send_redirects=0
net.ipv4.conf.default.send_redirects=0

# Process and kernel hardening
kernel.yama.ptrace_scope=1
kernel.kptr_restrict=2
kernel.dmesg_restrict=1
EOF
    sysctl -p "$SYSCTL_FILE"
    log "Kernel parameters optimized"
else
    skip "Kernel parameters already configured"
fi

# ---------------------------------------------------------------------------
# File descriptor limits
# ---------------------------------------------------------------------------
LIMITS_FILE="/etc/security/limits.d/99-arasul-limits.conf"
OLD_LIMITS_FILE="/etc/security/limits.d/99-jetson-dev.conf"

if [[ -f "$OLD_LIMITS_FILE" ]] && [[ ! -f "$LIMITS_FILE" ]]; then
    mv "$OLD_LIMITS_FILE" "$LIMITS_FILE"
    log "Renamed ${OLD_LIMITS_FILE} → ${LIMITS_FILE}"
fi

if [[ ! -f "$LIMITS_FILE" ]]; then
    cat > "$LIMITS_FILE" << EOF
${REAL_USER}    soft    nofile    65536
${REAL_USER}    hard    nofile    131072
${REAL_USER}    soft    nproc     65536
${REAL_USER}    hard    nproc     65536
EOF
    log "File descriptor limits raised for ${REAL_USER}"
else
    skip "File descriptor limits already set"
fi

# ---------------------------------------------------------------------------
# Journald size and retention limits
# ---------------------------------------------------------------------------
JOURNALD_DIR="/etc/systemd/journald.conf.d"
JOURNALD_CONF="${JOURNALD_DIR}/99-arasul.conf"
OLD_JOURNALD_CONF="${JOURNALD_DIR}/99-jetson.conf"

if [[ -f "$OLD_JOURNALD_CONF" ]] && [[ ! -f "$JOURNALD_CONF" ]]; then
    mv "$OLD_JOURNALD_CONF" "$JOURNALD_CONF"
    log "Renamed ${OLD_JOURNALD_CONF} → ${JOURNALD_CONF}"
fi

if [[ ! -f "$JOURNALD_CONF" ]]; then
    mkdir -p "$JOURNALD_DIR"
    cat > "$JOURNALD_CONF" << 'EOF'
[Journal]
SystemMaxUse=200M
MaxRetentionSec=1week
EOF
    systemctl restart systemd-journald
    log "Journald limited to 200MB / 1 week retention"
else
    skip "Journald limits already configured"
fi

# ---------------------------------------------------------------------------
# OOM protection for critical services
# ---------------------------------------------------------------------------
# Detect SSH service name (ssh.service on Ubuntu 22.04+, sshd.service on older/other)
if systemctl cat ssh.service &>/dev/null; then
    SSH_SERVICE="ssh"
elif systemctl cat sshd.service &>/dev/null; then
    SSH_SERVICE="sshd"
else
    SSH_SERVICE="ssh"
fi
SSH_OOM_DIR="/etc/systemd/system/${SSH_SERVICE}.service.d"
if [[ ! -f "${SSH_OOM_DIR}/oom.conf" ]]; then
    mkdir -p "$SSH_OOM_DIR"
    cat > "${SSH_OOM_DIR}/oom.conf" << 'EOF'
[Service]
OOMScoreAdjust=-900
EOF
    log "OOM protection set for ${SSH_SERVICE} (score -900)"
else
    skip "SSH OOM protection already configured"
fi

DOCKER_OOM_DIR="/etc/systemd/system/docker.service.d"
if [[ ! -f "${DOCKER_OOM_DIR}/oom.conf" ]]; then
    mkdir -p "$DOCKER_OOM_DIR"
    cat > "${DOCKER_OOM_DIR}/oom.conf" << 'EOF'
[Service]
OOMScoreAdjust=-500
EOF
    log "OOM protection set for Docker (score -500)"
else
    skip "Docker OOM protection already configured"
fi

systemctl daemon-reload

# ---------------------------------------------------------------------------
# Automatic security updates (unattended-upgrades)
# ---------------------------------------------------------------------------
if ! dpkg -l unattended-upgrades 2>/dev/null | grep -q "^ii"; then
    apt-get install -y -qq unattended-upgrades
fi

UNATTENDED_CONF="/etc/apt/apt.conf.d/50unattended-upgrades"
if [[ ! -f "$UNATTENDED_CONF" ]] || ! grep -qE "Package-(Blacklist|Blocklist)" "$UNATTENDED_CONF" 2>/dev/null; then
    cat > "$UNATTENDED_CONF" << 'EOF'
Unattended-Upgrade::Allowed-Origins {
    "${distro_id}:${distro_codename}-security";
};
// Exclude Docker and NVIDIA packages from auto-updates
Unattended-Upgrade::Package-Blacklist {
    "docker*";
    "nvidia*";
    "libnvidia*";
};
EOF
    systemctl enable --now unattended-upgrades
    log "Automatic security updates configured (Docker/NVIDIA excluded)"
else
    skip "Unattended-upgrades already configured"
fi

log "System optimization complete"
log "Free RAM: $(free -h | awk '/^Mem:/{print $7}')"
