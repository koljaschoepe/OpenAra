#!/usr/bin/env bash
# =============================================================================
# 02 — Network Setup
# Hostname, mDNS (Bonjour), UFW firewall, optional Tailscale, optional static IP
# =============================================================================
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

# shellcheck source=../lib/common.sh
source "$(dirname "$0")/../lib/common.sh"

# shellcheck source=../lib/detect.sh
source "$(dirname "$0")/../lib/detect.sh"

# Defaults for standalone execution
SCRIPT_DIR="${SCRIPT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
REAL_USER="${REAL_USER:-$(logname 2>/dev/null || echo "${SUDO_USER:-$USER}")}"
REAL_HOME="${REAL_HOME:-$(get_real_home)}"
PLATFORM="${PLATFORM:-$(detect_platform)}"
DEVICE_HOSTNAME="${DEVICE_HOSTNAME:-$(hostname)}"
INSTALL_TAILSCALE="${INSTALL_TAILSCALE:-false}"

# ---------------------------------------------------------------------------
# Set hostname
# ---------------------------------------------------------------------------
CURRENT_HOSTNAME=$(hostnamectl --static)
if [[ "$CURRENT_HOSTNAME" != "$DEVICE_HOSTNAME" ]]; then
    hostnamectl set-hostname "$DEVICE_HOSTNAME"
    sed -i "/127.0.1.1/d" /etc/hosts
    echo "127.0.1.1    ${DEVICE_HOSTNAME}" >> /etc/hosts
    log "Hostname set: ${DEVICE_HOSTNAME}"
else
    skip "Hostname already ${DEVICE_HOSTNAME}"
fi

# ---------------------------------------------------------------------------
# mDNS (Avahi) — device reachable as <hostname>.local
# ---------------------------------------------------------------------------
if ! dpkg -l avahi-daemon 2>/dev/null | grep -q "^ii"; then
    apt-get install -y -qq avahi-daemon libnss-mdns
    log "Avahi (mDNS) installed"
fi

systemctl enable --now avahi-daemon 2>/dev/null || true
log "mDNS active — reachable as ${DEVICE_HOSTNAME}.local"

# ---------------------------------------------------------------------------
# UFW Firewall
# ---------------------------------------------------------------------------
if ! command -v ufw &>/dev/null; then
    apt-get install -y -qq ufw
fi

if ! ufw status | grep -q "active"; then
    ufw default deny incoming
    ufw default allow outgoing
    ufw limit ssh comment 'SSH rate-limited'
    ufw allow 5353/udp comment 'mDNS'
    ufw --force enable
    log "UFW firewall enabled (SSH rate-limited + mDNS only)"
else
    skip "UFW already active"
fi

# ---------------------------------------------------------------------------
# Static IP (optional)
# ---------------------------------------------------------------------------
if [[ -n "${STATIC_IP:-}" ]]; then
    local_connection=$(nmcli -t -f NAME,TYPE connection show --active | grep ethernet | head -1 | cut -d: -f1)
    if [[ -n "$local_connection" ]]; then
        nmcli connection modify "$local_connection" \
            ipv4.method manual \
            ipv4.addresses "$STATIC_IP" \
            ipv4.gateway "${STATIC_GATEWAY:-}" \
            ipv4.dns "8.8.8.8,1.1.1.1"
        nmcli connection up "$local_connection"
        log "Static IP configured: ${STATIC_IP}"
    else
        warn "No active Ethernet connection found for static IP"
    fi
fi

# ---------------------------------------------------------------------------
# Network info
# ---------------------------------------------------------------------------
DEFAULT_IFACE=$(ip route show default 2>/dev/null | awk '/default/{print $5; exit}')
DEFAULT_IFACE="${DEFAULT_IFACE:-eth0}"
ETH_IP=$(ip -4 addr show "$DEFAULT_IFACE" 2>/dev/null | awk '/inet / {split($2,a,"/"); print a[1]; exit}')
ETH_IP="${ETH_IP:-not connected}"
log "Ethernet IP: ${ETH_IP}"
log "mDNS: ${DEVICE_HOSTNAME}.local"

# ---------------------------------------------------------------------------
# Tailscale (optional)
# ---------------------------------------------------------------------------
if [[ "${INSTALL_TAILSCALE}" == "true" ]]; then
    if ! command -v tailscale &>/dev/null; then
        log "Installing Tailscale..."
        curl -fsSL https://tailscale.com/install.sh | sh
        log "Tailscale installed"
        warn "Authentication required: sudo tailscale up"
        warn "Then disable key expiry in the Tailscale admin console"
    else
        skip "Tailscale already installed"
        if tailscale status &>/dev/null; then
            TS_IP=$(tailscale ip -4 2>/dev/null || echo "not connected")
            log "Tailscale IP: ${TS_IP}"
        else
            warn "Tailscale installed but not connected: sudo tailscale up"
        fi
    fi
else
    log "Tailscale skipped (INSTALL_TAILSCALE=false)"
fi

# ---------------------------------------------------------------------------
# WiFi power save (RPi only — prevents SSH disconnects over WiFi)
# ---------------------------------------------------------------------------
if [[ "${PLATFORM:-}" == "raspberry_pi" ]]; then
    # Detect WiFi interface dynamically (wlan0, wlp1s0, etc.)
    WIFI_IFACE=$(iw dev 2>/dev/null | awk '/Interface/{print $2; exit}')
    if [[ -n "${WIFI_IFACE:-}" ]] && iw "$WIFI_IFACE" get power_save 2>/dev/null | grep -q "on"; then
        iw "$WIFI_IFACE" set power_save off
        log "WiFi power save disabled (prevents SSH drops)"

        # Persist via NetworkManager (Bookworm+)
        if [[ -d /etc/NetworkManager/conf.d ]]; then
            cat > /etc/NetworkManager/conf.d/99-arasul-wifi.conf << 'WIFI'
[connection]
wifi.powersave = 2
WIFI
            log "WiFi power save config persisted"
        fi
    else
        skip "WiFi power save already off (or no WiFi)"
    fi
fi

log "Network setup complete"
