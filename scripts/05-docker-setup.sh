#!/usr/bin/env bash
# =============================================================================
# 05 — Docker Setup (Multi-Platform)
# Docker, optional NVIDIA Container Runtime, Compose V2
# Data root on external storage if available.
# =============================================================================
set -euo pipefail

# shellcheck source=../lib/common.sh
source "$(dirname "$0")/../lib/common.sh"

# shellcheck source=../lib/detect.sh
source "$(dirname "$0")/../lib/detect.sh"

PLATFORM="${PLATFORM:-$(detect_platform)}"
STORAGE_MOUNT="${STORAGE_MOUNT:-$(detect_storage_mount)}"
REAL_USER="${REAL_USER:-$(logname 2>/dev/null || echo "${SUDO_USER:-$USER}")}"
DOCKER_LOG_MAX_SIZE="${DOCKER_LOG_MAX_SIZE:-10m}"
DOCKER_LOG_MAX_FILES="${DOCKER_LOG_MAX_FILES:-3}"

# ---------------------------------------------------------------------------
# RPi: Enable cgroup memory (required for Docker memory limits)
# ---------------------------------------------------------------------------
if [[ "$PLATFORM" == "raspberry_pi" ]]; then
    # Bookworm+ uses /boot/firmware/, older uses /boot/
    cmdline=""
    if [[ -f /boot/firmware/cmdline.txt ]]; then
        cmdline="/boot/firmware/cmdline.txt"
    elif [[ -f /boot/cmdline.txt ]]; then
        cmdline="/boot/cmdline.txt"
    fi

    if [[ -n "$cmdline" ]] && ! grep -q "cgroup_enable=memory" "$cmdline"; then
        sed -i 's/$/ cgroup_enable=memory cgroup_memory=1/' "$cmdline"
        log "cgroup memory enabled in ${cmdline} (reboot required)"
    fi
fi

# ---------------------------------------------------------------------------
# Install Docker
# ---------------------------------------------------------------------------
if ! command -v docker &>/dev/null; then
    log "Installing Docker..."
    if has_nvidia_gpu 2>/dev/null; then
        apt-get install -y -qq docker.io nvidia-container-toolkit 2>/dev/null || {
            warn "Fallback: installing Docker manually..."
            curl -fsSL https://get.docker.com | sh
            apt-get install -y -qq nvidia-container-toolkit 2>/dev/null || true
        }
    else
        apt-get install -y -qq docker.io 2>/dev/null || {
            warn "Fallback: installing Docker manually..."
            curl -fsSL https://get.docker.com | sh
        }
    fi
fi

DOCKER_VERSION=$(docker --version 2>/dev/null | awk '{print $3}' | tr -d ',')
log "Docker version: ${DOCKER_VERSION}"

# Docker 28.x kernel issue is Jetson/JetPack specific
if [[ "$PLATFORM" == "jetson" ]] && [[ "$DOCKER_VERSION" == 28.* ]]; then
    warn "Docker 28.x detected — known kernel issues on JetPack 6.x!"
    warn "Downgrade to 27.5.x recommended"
fi

# ---------------------------------------------------------------------------
# Add user to docker group
# ---------------------------------------------------------------------------
if ! groups "$REAL_USER" | grep -q docker; then
    usermod -aG docker "$REAL_USER"
    log "${REAL_USER} added to docker group"
    warn "Log out and back in for group change to take effect"
else
    skip "${REAL_USER} already in docker group"
fi

# ---------------------------------------------------------------------------
# Configure Docker daemon
# ---------------------------------------------------------------------------
DAEMON_JSON="/etc/docker/daemon.json"

# Determine data root: prefer external storage
if [[ -d "$STORAGE_MOUNT" ]] && mountpoint -q "$STORAGE_MOUNT" 2>/dev/null; then
    DATA_ROOT="${STORAGE_MOUNT}/docker"
    mkdir -p "$DATA_ROOT"
else
    DATA_ROOT="/var/lib/docker"
    warn "External storage not mounted — Docker data stays on root filesystem"
fi

# Build desired config as a temp file, then merge with existing
DESIRED_JSON=$(mktemp)
if has_nvidia_gpu 2>/dev/null; then
    cat > "$DESIRED_JSON" << EOF
{
    "runtimes": {
        "nvidia": {
            "path": "nvidia-container-runtime",
            "runtimeArgs": []
        }
    },
    "default-runtime": "nvidia",
    "data-root": "${DATA_ROOT}",
    "log-driver": "json-file",
    "log-opts": {
        "max-size": "${DOCKER_LOG_MAX_SIZE}",
        "max-file": "${DOCKER_LOG_MAX_FILES}"
    },
    "storage-driver": "overlay2",
    "live-restore": true,
    "default-address-pools": [
        {"base": "172.17.0.0/12", "size": 24}
    ]
}
EOF
else
    cat > "$DESIRED_JSON" << EOF
{
    "data-root": "${DATA_ROOT}",
    "log-driver": "json-file",
    "log-opts": {
        "max-size": "${DOCKER_LOG_MAX_SIZE}",
        "max-file": "${DOCKER_LOG_MAX_FILES}"
    },
    "storage-driver": "overlay2",
    "live-restore": true,
    "default-address-pools": [
        {"base": "172.17.0.0/12", "size": 24}
    ]
}
EOF
fi

mkdir -p /etc/docker
if [[ -f "$DAEMON_JSON" ]] && [[ -s "$DAEMON_JSON" ]]; then
    # Merge: existing config takes lower priority, our keys win
    if command -v python3 &>/dev/null; then
        python3 -c "
import json, sys
with open('$DAEMON_JSON') as f:
    existing = json.load(f)
with open('$DESIRED_JSON') as f:
    desired = json.load(f)
# Deep merge: desired overwrites existing for top-level keys
merged = {**existing, **desired}
# Preserve any extra runtimes from existing config
if 'runtimes' in existing and 'runtimes' in desired:
    merged['runtimes'] = {**existing['runtimes'], **desired['runtimes']}
with open('$DAEMON_JSON', 'w') as f:
    json.dump(merged, f, indent=4)
    f.write('\n')
" && log "Docker daemon.json merged with existing config (data-root: ${DATA_ROOT})"
    else
        # No python3 — overwrite (safe: we're installing Docker anyway)
        cp "$DESIRED_JSON" "$DAEMON_JSON"
        log "Docker daemon.json written (data-root: ${DATA_ROOT})"
    fi
else
    cp "$DESIRED_JSON" "$DAEMON_JSON"
    if has_nvidia_gpu 2>/dev/null; then
        log "Docker daemon configured with NVIDIA runtime (data-root: ${DATA_ROOT})"
    else
        log "Docker daemon configured (data-root: ${DATA_ROOT})"
    fi
fi
rm -f "$DESIRED_JSON"

# ---------------------------------------------------------------------------
# Pin Docker version (prevent auto-upgrade to 28.x on Jetson)
# ---------------------------------------------------------------------------
if [[ "$PLATFORM" == "jetson" ]]; then
    apt-mark hold docker-ce docker-ce-cli 2>/dev/null || \
        apt-mark hold docker.io 2>/dev/null || true
    log "Docker version pinned against auto-upgrade (Jetson)"
fi

# ---------------------------------------------------------------------------
# Docker Compose V2
# ---------------------------------------------------------------------------
if ! docker compose version &>/dev/null 2>&1; then
    apt-get install -y -qq docker-compose-plugin 2>/dev/null || {
        COMPOSE_VERSION=$(curl -s https://api.github.com/repos/docker/compose/releases/latest | grep -oP '"tag_name":\s*"\K[^"]+')
        COMPOSE_ARCH=$(uname -m)
        mkdir -p /usr/local/lib/docker/cli-plugins
        curl -SL "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-linux-${COMPOSE_ARCH}" \
            -o /usr/local/lib/docker/cli-plugins/docker-compose
        chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
    }
    log "Docker Compose V2 installed"
else
    skip "Docker Compose V2 already present"
fi

# ---------------------------------------------------------------------------
# Restart Docker
# ---------------------------------------------------------------------------
systemctl daemon-reload
systemctl enable docker
systemctl restart docker

# Verify NVIDIA runtime (only if GPU present)
if has_nvidia_gpu 2>/dev/null; then
    if docker info 2>/dev/null | grep -q nvidia; then
        log "NVIDIA Container Runtime verified"
    else
        warn "NVIDIA Runtime not detected — GPU access in containers may not work"
    fi
fi

COMPOSE_VER=$(docker compose version 2>/dev/null | awk '{print $NF}' || echo "n/a")
log "Docker setup complete"
log "  Data Root: ${DATA_ROOT}"
if has_nvidia_gpu 2>/dev/null; then
    log "  Runtime:   nvidia (default)"
fi
log "  Compose:   ${COMPOSE_VER}"
