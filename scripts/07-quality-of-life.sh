#!/usr/bin/env bash
# =============================================================================
# 07 — Quality of Life (Multi-Platform)
# tmux, shell aliases, power mode (Jetson), MOTD, bash prompt
# =============================================================================
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

# shellcheck source=../lib/common.sh
source "$(dirname "$0")/../lib/common.sh"

# shellcheck source=../lib/detect.sh
source "$(dirname "$0")/../lib/detect.sh"

PLATFORM="${PLATFORM:-$(detect_platform)}"
REAL_USER="${REAL_USER:-$(logname 2>/dev/null || echo "${SUDO_USER:-$USER}")}"
REAL_HOME="${REAL_HOME:-$(get_real_home)}"
STORAGE_MOUNT="${STORAGE_MOUNT:-$(detect_storage_mount)}"
SCRIPT_DIR="${SCRIPT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
BASHRC="${REAL_HOME}/.bashrc"
POWER_MODE="${POWER_MODE:-3}"

check_root

# ---------------------------------------------------------------------------
# Ensure package index is current (needed for standalone execution)
# ---------------------------------------------------------------------------
apt-get update -qq 2>/dev/null || warn "apt-get update failed — packages may be stale"

# ---------------------------------------------------------------------------
# tmux
# ---------------------------------------------------------------------------
if ! command -v tmux &>/dev/null; then
    apt-get install -y -qq tmux
    log "tmux installed"
else
    skip "tmux already installed"
fi

TMUX_CONF="${REAL_HOME}/.tmux.conf"
if [[ -f "${SCRIPT_DIR}/config/tmux.conf" ]] && [[ ! -f "$TMUX_CONF" ]]; then
    cp "${SCRIPT_DIR}/config/tmux.conf" "$TMUX_CONF"
    chown "${REAL_USER}:${REAL_USER}" "$TMUX_CONF"
    log "tmux configuration installed"
else
    skip "tmux config already exists"
fi

# tmux Plugin Manager
TPM_DIR="${REAL_HOME}/.tmux/plugins/tpm"
if [[ ! -d "$TPM_DIR" ]]; then
    if run_as_user "git clone https://github.com/tmux-plugins/tpm '${TPM_DIR}'" 2>/dev/null; then
        log "tmux Plugin Manager installed (Ctrl-a I to install plugins)"
    else
        warn "Failed to install TPM (GitHub may be unreachable)"
    fi
fi

# ---------------------------------------------------------------------------
# Shell aliases (assembled from common + platform-specific)
# ---------------------------------------------------------------------------
ALIASES_FILE="${REAL_HOME}/.bash_aliases"
ALIASES_DIR="${SCRIPT_DIR}/config/aliases"

if [[ ! -f "$ALIASES_FILE" ]]; then
    # Build aliases from split files
    if [[ -f "${ALIASES_DIR}/common" ]]; then
        cat "${ALIASES_DIR}/common" > "$ALIASES_FILE"

        # Append platform-specific aliases
        if [[ -f "${ALIASES_DIR}/${PLATFORM}" ]]; then
            echo "" >> "$ALIASES_FILE"
            cat "${ALIASES_DIR}/${PLATFORM}" >> "$ALIASES_FILE"
        fi

        # Substitute storage mount placeholder (use # delimiter — paths may contain |)
        sed -i "s#__STORAGE_MOUNT__#${STORAGE_MOUNT}#g" "$ALIASES_FILE"

        chown "${REAL_USER}:${REAL_USER}" "$ALIASES_FILE"
        log "Shell aliases installed (common + ${PLATFORM})"
    else
        warn "Alias source files not found in ${ALIASES_DIR}"
    fi
else
    skip "Shell aliases already exist"
fi

# Ensure .bashrc sources .bash_aliases (default on Debian/Ubuntu, but verify)
if [[ -f "$ALIASES_FILE" ]] && ! grep -q "bash_aliases" "$BASHRC" 2>/dev/null; then
    cat >> "$BASHRC" << 'ALIASES_SOURCE'

# Source aliases
if [ -f ~/.bash_aliases ]; then
    . ~/.bash_aliases
fi
ALIASES_SOURCE
    chown "${REAL_USER}:${REAL_USER}" "$BASHRC"
    log "Added .bash_aliases sourcing to .bashrc"
fi

# ---------------------------------------------------------------------------
# Bash prompt with device context
# ---------------------------------------------------------------------------
if ! grep -q "arasul-prompt" "$BASHRC" 2>/dev/null; then
    # Remove old jetson-prompt if present (upgrade path)
    # Use line-by-line deletion instead of range to avoid deleting to EOF if end pattern is missing
    if grep -q "jetson-prompt" "$BASHRC" 2>/dev/null; then
        sed -i '/# jetson-prompt/d;/__jetson_ps1/d;/PROMPT_COMMAND=.*__jetson_ps1/d' "$BASHRC" 2>/dev/null || true
        log "Removed old jetson-prompt from .bashrc"
    fi

    cat >> "$BASHRC" << 'PROMPT'

# arasul-prompt
__arasul_ps1() {
    local git_branch=$(git symbolic-ref --short HEAD 2>/dev/null)
    local ram_used=$(free -m | awk '/^Mem:/{printf "%.1fG", $3/1024}')

    # Use \001/\002 (raw RL_PROMPT_START/END) instead of \[/\] for PROMPT_COMMAND
    if [[ -n "$git_branch" ]]; then
        echo -e "\001\033[32m\002\u@\h\001\033[0m\002:\001\033[34m\002\w\001\033[33m\002 ($git_branch)\001\033[36m\002 [${ram_used}]\001\033[0m\002\$ "
    else
        echo -e "\001\033[32m\002\u@\h\001\033[0m\002:\001\033[34m\002\w\001\033[36m\002 [${ram_used}]\001\033[0m\002\$ "
    fi
}
PROMPT_COMMAND='PS1=$(__arasul_ps1)'
PROMPT
    chown "${REAL_USER}:${REAL_USER}" "$BASHRC"
    log "Custom bash prompt installed"
fi

# ---------------------------------------------------------------------------
# Power mode (Jetson only)
# ---------------------------------------------------------------------------
if [[ "$PLATFORM" == "jetson" ]] && command -v nvpmodel &>/dev/null; then
    CURRENT_MODE=$(nvpmodel -q 2>/dev/null | grep "NV Power Mode" | awk -F: '{print $2}' | xargs || true)
    nvpmodel -m "${POWER_MODE:-3}" 2>/dev/null || true
    log "Power mode set: ${POWER_MODE:-3} (was: ${CURRENT_MODE:-unknown})"
fi

# ---------------------------------------------------------------------------
# MOTD — platform-aware login banner
# ---------------------------------------------------------------------------
chmod -x /etc/update-motd.d/* 2>/dev/null || true

MOTD_SRC="${SCRIPT_DIR}/config/motd-arasul"
MOTD_DST="/etc/update-motd.d/10-arasul"
if [[ -f "$MOTD_SRC" ]]; then
    cp "$MOTD_SRC" "$MOTD_DST"
    chmod +x "$MOTD_DST"

    # RPi OS uses PAM motd, not update-motd.d — also write static /etc/motd
    if [[ "$PLATFORM" == "raspberry_pi" ]] || [[ ! -x /etc/update-motd.d/10-arasul ]] \
       || ! grep -q "update-motd\|pam_exec.*motd" /etc/pam.d/sshd 2>/dev/null; then
        # Generate static MOTD as fallback for systems without update-motd.d support
        bash "$MOTD_DST" > /etc/motd 2>/dev/null || true
        log "Arasul MOTD installed (static /etc/motd for ${PLATFORM})"
    else
        log "Arasul MOTD installed (dynamic update-motd.d)"
    fi
else
    log "MOTD disabled (Arasul Shell takes over)"
fi

# Arasul Shell auto-start on SSH login
if ! grep -q "ARASUL_SHELL_ACTIVE" "$BASHRC" 2>/dev/null; then
    cat >> "$BASHRC" << 'AUTOSTART'

# Auto-start Arasul Shell on interactive SSH login
if [ -n "$SSH_CONNECTION" ] && [ -z "$ARASUL_SHELL_ACTIVE" ] && [ -t 0 ] && command -v arasul &>/dev/null; then
    export ARASUL_SHELL_ACTIVE=1
    arasul || true
fi
AUTOSTART
    chown "${REAL_USER}:${REAL_USER}" "$BASHRC"
    log "Arasul Shell auto-start configured"
fi

# ---------------------------------------------------------------------------
# Install Arasul TUI (optional)
# ---------------------------------------------------------------------------
if [[ "${INSTALL_ARASUL_TUI:-true}" == "true" ]]; then
    if [[ -d "${SCRIPT_DIR}/arasul_tui" ]] && [[ -f "${SCRIPT_DIR}/pyproject.toml" ]]; then
        # Install TUI as normal user (venv + pip install)
        run_as_user "bash '${SCRIPT_DIR}/arasul_tui/install.sh'" && log "Arasul TUI installed"

        # Create launcher as root (install.sh's sudo tee may fail inside run_as_user)
        cat > /usr/local/bin/arasul << LAUNCHER
#!/usr/bin/env bash
exec "${REAL_HOME}/venvs/arasul/bin/arasul" "\$@"
LAUNCHER
        chmod +x /usr/local/bin/arasul
        log "Launcher installed: /usr/local/bin/arasul"
    else
        warn "Arasul TUI sources not found in repo — skipping installation"
    fi
else
    skip "Arasul TUI installation disabled"
fi

log "Quality of life setup complete"
