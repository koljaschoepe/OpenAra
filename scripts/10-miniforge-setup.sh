#!/usr/bin/env bash
# =============================================================================
# 10 — Miniforge3 Setup (Lazy Install)
# Installs Miniforge3 on storage for per-project conda environments.
# NOT called by setup.sh — only triggered on first template project creation.
# =============================================================================
set -euo pipefail

# shellcheck source=../lib/common.sh
source "$(dirname "$0")/../lib/common.sh"

# shellcheck source=../lib/detect.sh
source "$(dirname "$0")/../lib/detect.sh"

# Defaults for standalone execution
REAL_USER="${REAL_USER:-$(logname 2>/dev/null || echo "${SUDO_USER:-$USER}")}"
STORAGE_MOUNT="${STORAGE_MOUNT:-$(detect_storage_mount)}"

MINIFORGE_DIR="${STORAGE_MOUNT}/miniforge3"
ENVS_DIR="${STORAGE_MOUNT}/envs"
ARCH="$(uname -m)"
INSTALLER_URL="https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-${ARCH}.sh"
INSTALLER_PATH="/tmp/miniforge3-installer.sh"

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

if [[ -d "$MINIFORGE_DIR" ]] && [[ -x "$MINIFORGE_DIR/bin/conda" ]]; then
    skip "Miniforge3 already installed at $MINIFORGE_DIR"
    exit 0
fi

STORAGE_BASE="${STORAGE_MOUNT}"
if [[ ! -d "$STORAGE_BASE" ]]; then
    err "Storage not available at $STORAGE_BASE — required for Miniforge3"
    exit 1
fi

check_internet || {
    err "Internet required to download Miniforge3"
    exit 1
}

# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------
step "Installing Miniforge3 (${ARCH})"

log "Downloading Miniforge3..."
curl -fSL "$INSTALLER_URL" -o "$INSTALLER_PATH"
chmod +x "$INSTALLER_PATH"

# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------
log "Installing to $MINIFORGE_DIR..."
bash "$INSTALLER_PATH" -b -p "$MINIFORGE_DIR"
rm -f "$INSTALLER_PATH"

# Set ownership if running as root
if [[ $EUID -eq 0 ]] && [[ -n "${REAL_USER:-}" ]]; then
    chown -R "${REAL_USER}:${REAL_USER}" "$MINIFORGE_DIR"
fi

# ---------------------------------------------------------------------------
# Configure (without global activation)
# ---------------------------------------------------------------------------
log "Configuring conda (no global activation)..."

# Initialize conda for the user's shell but disable auto-activation
"$MINIFORGE_DIR/bin/conda" config --set auto_activate_base false
"$MINIFORGE_DIR/bin/conda" config --set envs_dirs "$ENVS_DIR"

# Create shared envs directory
mkdir -p "$ENVS_DIR"
if [[ $EUID -eq 0 ]] && [[ -n "${REAL_USER:-}" ]]; then
    chown "${REAL_USER}:${REAL_USER}" "$ENVS_DIR"
fi

# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------
CONDA_VER=$("$MINIFORGE_DIR/bin/conda" --version 2>/dev/null || echo "unknown")
PYTHON_VER=$("$MINIFORGE_DIR/bin/python" --version 2>/dev/null || echo "unknown")

log "Miniforge3 setup complete"
log "  Conda:   $CONDA_VER"
log "  Python:  $PYTHON_VER"
log "  Path:    $MINIFORGE_DIR"
log "  Envs:    $ENVS_DIR"
