#!/usr/bin/env bash
# =============================================================================
# Shared shell library for all setup scripts
# Source this file: source "$(dirname "$0")/../lib/common.sh"
# =============================================================================

# Color constants
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Logging functions
log()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[✗]${NC} $*" >&2; }
skip() { echo -e "${YELLOW}[→]${NC} $* (already done)"; }
info() { echo -e "${CYAN}[i]${NC} $*"; }
step() { echo -e "\n${BLUE}═══════════════════════════════════════════════${NC}"; echo -e "${BLUE}  $*${NC}"; echo -e "${BLUE}═══════════════════════════════════════════════${NC}\n"; }

# Run a command as the non-root user
# Usage: run_as_user "command with args" (passed as single string to bash -c)
run_as_user() {
    sudo -u "$REAL_USER" -H -- bash -c "$1"
}

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        err "This script must be run with sudo"
        echo "  sudo $0"
        exit 1
    fi
}

# Check internet connectivity
check_internet() {
    if ! curl -s --connect-timeout 5 https://connectivity-check.ubuntu.com/ >/dev/null 2>&1; then
        warn "No internet connection detected"
        return 1
    fi
    return 0
}

# Check if a Debian package is installed
# Usage: is_pkg_installed "package-name"
is_pkg_installed() {
    dpkg -l "$1" 2>/dev/null | grep -q "^ii"
}

# Install packages with standard flags (quiet, non-interactive)
# Usage: apt_install package1 package2 ...
apt_install() {
    apt-get install -y -qq "$@"
}

# Create a directory owned by REAL_USER
# Usage: mkdir_as_user /path/to/dir
mkdir_as_user() {
    mkdir -p "$1"
    chown "${REAL_USER}:${REAL_USER}" "$1"
}

# Append a line to a file if a pattern is not already present
# Usage: append_if_missing "file" "grep_pattern" "line_to_append"
append_if_missing() {
    local file="$1" pattern="$2" content="$3"
    if ! grep -q "$pattern" "$file" 2>/dev/null; then
        echo "$content" >> "$file"
        return 0
    fi
    return 1
}
