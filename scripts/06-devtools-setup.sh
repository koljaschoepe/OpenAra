#!/usr/bin/env bash
# =============================================================================
# 06 — Development Tools (Multi-Platform)
# Node.js (nvm), Python venv, Git, Claude Code, jtop (Jetson only)
# =============================================================================
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

# shellcheck source=../lib/common.sh
source "$(dirname "$0")/../lib/common.sh"

# shellcheck source=../lib/detect.sh
source "$(dirname "$0")/../lib/detect.sh"

check_root

# Defaults for standalone execution
REAL_USER="${REAL_USER:-$(logname 2>/dev/null || echo "${SUDO_USER:-$USER}")}"
REAL_HOME="${REAL_HOME:-$(get_real_home)}"
PLATFORM="${PLATFORM:-$(detect_platform)}"
STORAGE_MOUNT="${STORAGE_MOUNT:-$(detect_storage_mount)}"
SCRIPT_DIR="${SCRIPT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
NODE_VERSION="${NODE_VERSION:-22}"
NVM_DIR="${REAL_HOME}/.nvm"
DEVICE_HOSTNAME="${DEVICE_HOSTNAME:-$(hostname)}"
CUSTOMER_NAME="${CUSTOMER_NAME:-arasul}"
INSTALL_CLAUDE="${INSTALL_CLAUDE:-true}"
INSTALL_OLLAMA="${INSTALL_OLLAMA:-false}"
GIT_USER_NAME="${GIT_USER_NAME:-}"
GIT_USER_EMAIL="${GIT_USER_EMAIL:-}"

# ---------------------------------------------------------------------------
# Ensure package index is current (needed for standalone execution)
# ---------------------------------------------------------------------------
apt-get update -qq 2>/dev/null || warn "apt-get update failed — packages may be stale"

# ---------------------------------------------------------------------------
# Build essentials (for native npm/pip packages)
# ---------------------------------------------------------------------------
log "Installing build tools..."
apt-get install -y -qq \
    build-essential \
    python3-dev \
    python3-venv \
    python3-pip \
    libffi-dev \
    libssl-dev \
    pkg-config \
    2>/dev/null

# ---------------------------------------------------------------------------
# Git
# ---------------------------------------------------------------------------
if ! command -v git &>/dev/null; then
    apt-get install -y -qq git
fi

if [[ -n "${GIT_USER_NAME:-}" ]] && [[ "$GIT_USER_NAME" != "CHANGEME" ]]; then
    sudo -u "$REAL_USER" -H git config --global user.name "$GIT_USER_NAME"
    if [[ -n "${GIT_USER_EMAIL:-}" ]] && [[ "$GIT_USER_EMAIL" != "CHANGEME" ]]; then
        sudo -u "$REAL_USER" -H git config --global user.email "$GIT_USER_EMAIL"
    fi
    log "Git configured: ${GIT_USER_NAME} <${GIT_USER_EMAIL:-not set}>"
else
    warn "Git user.name not set — configure manually:"
    warn "  git config --global user.name 'Your Name'"
    warn "  git config --global user.email 'you@example.com'"
fi

run_as_user "git config --global init.defaultBranch main"
run_as_user "git config --global pull.rebase true"
run_as_user "git config --global core.editor nano"

# GitHub SSH key
GH_KEY="${REAL_HOME}/.ssh/github_ed25519"
if [[ ! -f "$GH_KEY" ]]; then
    run_as_user "mkdir -p ${REAL_HOME}/.ssh && chmod 700 ${REAL_HOME}/.ssh"
    run_as_user "ssh-keygen -t ed25519 -C '${DEVICE_HOSTNAME}-${CUSTOMER_NAME}' -f ${GH_KEY} -N ''"
    log "GitHub SSH key generated: ${GH_KEY}"
    echo ""
    echo "  ┌──────────────────────────────────────────────────┐"
    echo "  │ Add this key to GitHub → Settings → SSH Keys:    │"
    echo "  └──────────────────────────────────────────────────┘"
    cat "${GH_KEY}.pub"
    echo ""
else
    skip "GitHub SSH key already exists"
fi

SSH_CONFIG="${REAL_HOME}/.ssh/config"
if ! grep -q "github.com" "$SSH_CONFIG" 2>/dev/null; then
    cat >> "$SSH_CONFIG" << EOF

Host github.com
    HostName github.com
    User git
    IdentityFile ${GH_KEY}
    IdentitiesOnly yes
EOF
    chown "${REAL_USER}:${REAL_USER}" "$SSH_CONFIG"
    chmod 600 "$SSH_CONFIG"
    log "SSH configured for GitHub"
fi

# ---------------------------------------------------------------------------
# Node.js via nvm
# ---------------------------------------------------------------------------
if [[ ! -d "$NVM_DIR" ]]; then
    log "Installing nvm + Node.js ${NODE_VERSION} LTS..."
    run_as_user "curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.4/install.sh | bash"
    if [[ ! -f "${NVM_DIR}/nvm.sh" ]]; then
        err "nvm installation failed — ${NVM_DIR}/nvm.sh not found"
        exit 1
    fi
    run_as_user "export NVM_DIR='${NVM_DIR}' && source '${NVM_DIR}/nvm.sh' && nvm install ${NODE_VERSION} && nvm alias default ${NODE_VERSION}"
    log "Node.js installed via nvm"
else
    skip "nvm already installed"
fi

NODE_VER=$(run_as_user "export NVM_DIR='${NVM_DIR}' && source '${NVM_DIR}/nvm.sh' && node --version" 2>/dev/null || echo "not found")
log "Node.js version: ${NODE_VER}"

# Create global symlinks so npx/node are available without sourcing nvm.sh
# (needed by Claude Code MCP subprocess spawning)
NPX_PATH=$(run_as_user "export NVM_DIR='${NVM_DIR}' && source '${NVM_DIR}/nvm.sh' && command -v npx" 2>/dev/null || true)
if [[ -n "$NPX_PATH" && -f "$NPX_PATH" ]]; then
    ln -sf "$NPX_PATH" /usr/local/bin/npx
    NODE_PATH=$(run_as_user "export NVM_DIR='${NVM_DIR}' && source '${NVM_DIR}/nvm.sh' && command -v node" 2>/dev/null || true)
    [[ -n "$NODE_PATH" && -f "$NODE_PATH" ]] && ln -sf "$NODE_PATH" /usr/local/bin/node
    log "Global symlinks created: /usr/local/bin/{node,npx}"
fi

# ---------------------------------------------------------------------------
# Python virtual environment
# ---------------------------------------------------------------------------
VENV_DIR="${REAL_HOME}/venvs/default"
if [[ ! -d "$VENV_DIR" ]]; then
    run_as_user "python3 -m venv '${VENV_DIR}' --system-site-packages"
    log "Python venv created: ${VENV_DIR}"
else
    skip "Python venv already exists"
fi

# ---------------------------------------------------------------------------
# Claude Code
# ---------------------------------------------------------------------------
if [[ "${INSTALL_CLAUDE}" == "true" ]]; then
    if run_as_user "export NVM_DIR='${NVM_DIR}' && source '${NVM_DIR}/nvm.sh' && command -v claude" &>/dev/null; then
        skip "Claude Code already installed"
    else
        log "Installing Claude Code..."
        if run_as_user "export NVM_DIR='${NVM_DIR}' && source '${NVM_DIR}/nvm.sh' && npm install -g @anthropic-ai/claude-code" 2>/dev/null; then
            log "Claude Code installed via npm"
        else
            warn "npm install failed — trying native installer..."
            run_as_user "curl -fsSL https://claude.ai/install.sh | bash" 2>/dev/null || {
                warn "Claude Code could not be installed"
                warn "Try manually: npm install -g @anthropic-ai/claude-code"
            }
        fi
    fi
else
    log "Claude Code skipped (INSTALL_CLAUDE=false)"
fi

# ---------------------------------------------------------------------------
# Ollama (optional — local LLM inference)
# ---------------------------------------------------------------------------
if [[ "${INSTALL_OLLAMA}" == "true" ]]; then
    if ! command -v ollama &>/dev/null; then
        log "Installing Ollama..."
        curl -fsSL https://ollama.com/install.sh | sh
        if ! command -v ollama &>/dev/null; then
            warn "Ollama installation failed — command not found after install"
        fi
        # Model directory on external storage (create if storage is available)
        if mountpoint -q "$STORAGE_MOUNT" 2>/dev/null || [[ -d "$STORAGE_MOUNT" ]]; then
            mkdir -p "${STORAGE_MOUNT}/models/ollama"
            mkdir -p /etc/systemd/system/ollama.service.d
            cat > /etc/systemd/system/ollama.service.d/override.conf << EOF
[Service]
Environment="OLLAMA_MODELS=${STORAGE_MOUNT}/models/ollama"
EOF
            systemctl daemon-reload
            systemctl restart ollama
            log "Ollama installed (models: ${STORAGE_MOUNT}/models/ollama)"
        else
            log "Ollama installed (models: default location)"
        fi
    else
        skip "Ollama already installed"
    fi
else
    log "Ollama skipped (INSTALL_OLLAMA=false)"
fi

# ---------------------------------------------------------------------------
# jtop (Jetson system monitor — Jetson only)
# ---------------------------------------------------------------------------
if [[ "$PLATFORM" == "jetson" ]]; then
    if ! command -v jtop &>/dev/null; then
        pip3 install --break-system-packages -U jetson-stats 2>/dev/null || \
            pip3 install -U jetson-stats 2>/dev/null || true
        log "jtop installed"
    else
        skip "jtop already installed"
    fi
fi

log "Development tools setup complete"
