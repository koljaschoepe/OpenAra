#!/usr/bin/env bash
# =============================================================================
# OpenAra — Remote Install Script
# =============================================================================
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/koljaschoepe/OpenAra/main/install.sh | bash
#
# Or inspect first:
#   curl -fsSL https://raw.githubusercontent.com/koljaschoepe/OpenAra/main/install.sh -o install.sh
#   less install.sh
#   bash install.sh
#
# Options (via environment variables):
#   OPENARA_VERSION=v0.5.0    Pin to a specific release (default: latest tag)
#   OPENARA_DIR=/opt/openara  Install location (default: /opt/openara)
#   OPENARA_AUTO=1            Skip wizard, use defaults (default: interactive)
# =============================================================================

set -euo pipefail

# Colors (if terminal supports them)
if [[ -t 1 ]]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    BLUE='\033[0;34m'
    DIM='\033[2m'
    BOLD='\033[1m'
    RESET='\033[0m'
else
    RED='' GREEN='' BLUE='' DIM='' BOLD='' RESET=''
fi

log()  { echo -e "${GREEN}[✓]${RESET} $*"; }
info() { echo -e "${BLUE}[i]${RESET} $*"; }
warn() { echo -e "${RED}[!]${RESET} $*"; }
err()  { echo -e "${RED}[✗]${RESET} $*" >&2; }

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
OPENARA_VERSION="${OPENARA_VERSION:-}"
OPENARA_DIR="${OPENARA_DIR:-/opt/openara}"
OPENARA_AUTO="${OPENARA_AUTO:-}"
REPO_URL="https://github.com/koljaschoepe/OpenAra.git"

echo ""
echo -e "${BOLD}  OpenAra Installer${RESET}"
echo -e "${DIM}  Turn any Linux SBC into a headless development server${RESET}"
echo ""

# Must be Linux
if [[ "$(uname -s)" != "Linux" ]]; then
    err "OpenAra requires Linux. Detected: $(uname -s)"
    err "Run this script on your Jetson, Raspberry Pi, or Linux server."
    exit 1
fi

# Must be root (or will need sudo for setup.sh)
if [[ $EUID -ne 0 ]]; then
    info "This script will use sudo for system setup."
    if ! command -v sudo &>/dev/null; then
        err "sudo is required. Please run as root or install sudo."
        exit 1
    fi
fi

# Must have git
if ! command -v git &>/dev/null; then
    info "Installing git..."
    if command -v apt-get &>/dev/null; then
        sudo apt-get update -qq && sudo apt-get install -y -qq git
    else
        err "git is required. Please install git and try again."
        exit 1
    fi
fi

# Detect architecture
ARCH=$(uname -m)
if [[ "$ARCH" != "aarch64" && "$ARCH" != "x86_64" ]]; then
    warn "Untested architecture: ${ARCH}. Proceeding anyway..."
fi

# ---------------------------------------------------------------------------
# Determine version
# ---------------------------------------------------------------------------
if [[ -z "$OPENARA_VERSION" ]]; then
    # Try to get latest tag from GitHub API
    if command -v curl &>/dev/null; then
        OPENARA_VERSION=$(curl -fsSL "https://api.github.com/repos/koljaschoepe/OpenAra/releases/latest" 2>/dev/null \
            | grep '"tag_name"' | head -1 | cut -d'"' -f4) || true
    fi
    if [[ -z "$OPENARA_VERSION" ]]; then
        OPENARA_VERSION="main"
        info "Could not detect latest release, using main branch"
    else
        info "Latest release: ${OPENARA_VERSION}"
    fi
else
    info "Pinned version: ${OPENARA_VERSION}"
fi

# ---------------------------------------------------------------------------
# Clone or update
# ---------------------------------------------------------------------------
_dir_owner() {
    stat -c '%U' "$1" 2>/dev/null || stat -f '%Su' "$1" 2>/dev/null || echo "root"
}

if [[ -d "${OPENARA_DIR}/.git" ]]; then
    info "Existing installation found at ${OPENARA_DIR}"
    info "Updating..."
    cd "$OPENARA_DIR"
    OWNER=$(_dir_owner "$OPENARA_DIR")
    sudo -u "$OWNER" git fetch origin
    if [[ "$OPENARA_VERSION" != "main" ]]; then
        sudo -u "$OWNER" git checkout "$OPENARA_VERSION"
    else
        sudo -u "$OWNER" git pull origin main
    fi
    log "Updated to ${OPENARA_VERSION}"
else
    # If directory exists but is not a git repo (e.g., failed previous install), remove it
    if [[ -d "$OPENARA_DIR" ]] && [[ -n "$(ls -A "$OPENARA_DIR" 2>/dev/null)" ]]; then
        warn "Directory ${OPENARA_DIR} exists but is not a git repo — removing..."
        sudo rm -rf "$OPENARA_DIR"
    fi

    info "Installing to ${OPENARA_DIR}..."
    sudo mkdir -p "$(dirname "$OPENARA_DIR")"

    if [[ "$OPENARA_VERSION" != "main" ]]; then
        sudo git clone --branch "$OPENARA_VERSION" --depth 1 "$REPO_URL" "$OPENARA_DIR"
    else
        sudo git clone --depth 1 "$REPO_URL" "$OPENARA_DIR"
    fi

    # Set ownership to the real user (not root)
    REAL_USER="${SUDO_USER:-$(whoami)}"
    sudo chown -R "${REAL_USER}:${REAL_USER}" "$OPENARA_DIR"
    log "Cloned to ${OPENARA_DIR}"
fi

cd "$OPENARA_DIR"

# ---------------------------------------------------------------------------
# Run setup
# ---------------------------------------------------------------------------
echo ""
info "Starting setup..."
echo ""

if [[ -n "$OPENARA_AUTO" ]]; then
    sudo ./setup.sh --auto
else
    sudo ./setup.sh
fi
