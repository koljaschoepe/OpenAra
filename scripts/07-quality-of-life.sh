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

        # Substitute storage mount placeholder
        sed -i "s|__STORAGE_MOUNT__|${STORAGE_MOUNT}|g" "$ALIASES_FILE"

        chown "${REAL_USER}:${REAL_USER}" "$ALIASES_FILE"
        log "Shell aliases installed (common + ${PLATFORM})"
    else
        warn "Alias source files not found in ${ALIASES_DIR}"
    fi
else
    skip "Shell aliases already exist"
fi

# ---------------------------------------------------------------------------
# Bash prompt with device context
# ---------------------------------------------------------------------------
BASHRC="${REAL_HOME}/.bashrc"
if ! grep -q "arasul-prompt" "$BASHRC" 2>/dev/null; then
    # Remove old jetson-prompt if present (upgrade path)
    if grep -q "jetson-prompt" "$BASHRC" 2>/dev/null; then
        sed -i '/# jetson-prompt/,/PROMPT_COMMAND=.*__jetson_ps1/d' "$BASHRC" 2>/dev/null || true
        log "Removed old jetson-prompt from .bashrc"
    fi

    cat >> "$BASHRC" << 'PROMPT'

# arasul-prompt
__arasul_ps1() {
    local git_branch=$(git symbolic-ref --short HEAD 2>/dev/null)
    local ram_used=$(free -m | awk '/^Mem:/{printf "%.1fG", $3/1024}')

    if [[ -n "$git_branch" ]]; then
        echo -e "\[\033[32m\]\u@\h\[\033[0m\]:\[\033[34m\]\w\[\033[33m\] ($git_branch)\[\033[36m\] [${ram_used}]\[\033[0m\]\$ "
    else
        echo -e "\[\033[32m\]\u@\h\[\033[0m\]:\[\033[34m\]\w\[\033[36m\] [${ram_used}]\[\033[0m\]\$ "
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
    nvpmodel -m "${POWER_MODE}" 2>/dev/null || true
    log "Power mode set: ${POWER_MODE} (was: ${CURRENT_MODE:-unknown})"
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
    log "Arasul MOTD installed (platform-aware)"
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
        cat > /usr/local/bin/arasul << 'LAUNCHER'
#!/usr/bin/env bash
exec "$HOME/venvs/arasul/bin/arasul" "$@"
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
