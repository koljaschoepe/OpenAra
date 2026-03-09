#!/usr/bin/env bash
# =============================================================================
# 08 — Headless Browser Setup (Playwright + Chromium)
# =============================================================================
# Installs Playwright with headless Chromium for AI agent browser automation.
# Installed in the Arasul TUI venv, cached on external storage if available.
#
# Idempotent: can be run multiple times, skips already completed steps.
# =============================================================================

set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

# shellcheck source=../lib/common.sh
source "$(dirname "$0")/../lib/common.sh"

# shellcheck source=../lib/detect.sh
source "$(dirname "$0")/../lib/detect.sh"

check_root

REAL_USER="${REAL_USER:-$(logname 2>/dev/null || echo "${SUDO_USER:-$USER}")}"
REAL_HOME="${REAL_HOME:-$(get_real_home)}"
STORAGE_MOUNT="${STORAGE_MOUNT:-$(detect_storage_mount)}"
VENV_DIR="${REAL_HOME}/venvs/arasul"
BROWSER_CACHE="${STORAGE_MOUNT}/playwright-browsers"

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
if [[ ! -d "$VENV_DIR" ]]; then
    err "Arasul TUI venv not found: ${VENV_DIR}"
    err "Please run arasul_tui/install.sh first."
    exit 1
fi

VENV_PIP="${VENV_DIR}/bin/pip"
VENV_PYTHON="${VENV_DIR}/bin/python"

# ---------------------------------------------------------------------------
# 1. System dependencies for Chromium (headless)
# ---------------------------------------------------------------------------
install_system_deps() {
    log "Installing system dependencies for headless Chromium..."
    apt-get update -qq
    apt-get install -y -qq \
        libnss3 \
        libnspr4 \
        libatk1.0-0 \
        libatk-bridge2.0-0 \
        libcups2 \
        libdrm2 \
        libdbus-1-3 \
        libxkbcommon0 \
        libatspi2.0-0 \
        libxcomposite1 \
        libxdamage1 \
        libxfixes3 \
        libxrandr2 \
        libgbm1 \
        libpango-1.0-0 \
        libcairo2 \
        libwayland-client0 \
        > /dev/null 2>&1
    # libasound2 was renamed to libasound2t64 in newer Ubuntu/Debian
    apt-get install -y -qq libasound2 > /dev/null 2>&1 || \
        apt-get install -y -qq libasound2t64 > /dev/null 2>&1 || true
    log "System dependencies installed."
}

# ---------------------------------------------------------------------------
# 2. Install Playwright Python package
# ---------------------------------------------------------------------------
install_playwright_package() {
    if "${VENV_PYTHON}" -c "import playwright" 2>/dev/null; then
        local version
        version=$("${VENV_PYTHON}" -c "import playwright; print(playwright.__version__)" 2>/dev/null)
        log "Playwright Python already installed (v${version})"
        return 0
    fi

    log "Installing Playwright Python into venv..."
    sudo -u "$REAL_USER" "${VENV_PIP}" install --quiet playwright
    local version
    version=$("${VENV_PYTHON}" -c "import playwright; print(playwright.__version__)" 2>/dev/null)
    log "Playwright v${version} installed."
}

# ---------------------------------------------------------------------------
# 3. Set up browser cache on storage
# ---------------------------------------------------------------------------
setup_browser_cache() {
    if [[ -d "$BROWSER_CACHE" ]]; then
        log "Browser cache already exists: ${BROWSER_CACHE}"
    else
        log "Creating browser cache: ${BROWSER_CACHE}"
        mkdir -p "$BROWSER_CACHE"
        chown "${REAL_USER}:${REAL_USER}" "$BROWSER_CACHE"
    fi

    # Always ensure the env var is in .bashrc (even if cache dir already existed)
    local bashrc="${REAL_HOME}/.bashrc"
    if ! grep -q "PLAYWRIGHT_BROWSERS_PATH" "$bashrc" 2>/dev/null; then
        echo "" >> "$bashrc"
        echo "export PLAYWRIGHT_BROWSERS_PATH=\"${BROWSER_CACHE}\"" >> "$bashrc"
        log "PLAYWRIGHT_BROWSERS_PATH added to .bashrc."
    fi
}

# ---------------------------------------------------------------------------
# 4. Download Chromium
# ---------------------------------------------------------------------------
install_chromium() {
    export PLAYWRIGHT_BROWSERS_PATH="$BROWSER_CACHE"

    local chromium_dir
    chromium_dir=$(find "$BROWSER_CACHE" -maxdepth 4 -name "chrome" -type f 2>/dev/null | head -1)
    if [[ -n "$chromium_dir" ]]; then
        log "Chromium already downloaded in ${BROWSER_CACHE}"
        return 0
    fi

    log "Downloading Chromium (ARM64, ~180MB)..."
    sudo -u "$REAL_USER" \
        PLAYWRIGHT_BROWSERS_PATH="$BROWSER_CACHE" \
        "${VENV_PYTHON}" -m playwright install chromium
    log "Chromium downloaded to ${BROWSER_CACHE}"
}

# ---------------------------------------------------------------------------
# 5. Set up MCP config for Claude Code
# ---------------------------------------------------------------------------
setup_mcp_config() {
    local claude_json="${REAL_HOME}/.claude.json"

    if "${VENV_PYTHON}" - "$claude_json" <<'CHECKEOF' 2>/dev/null; then
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    mcp = d.get('mcpServers', {})
    if 'playwright' in mcp:
        sys.exit(0)
    sys.exit(1)
except Exception:
    sys.exit(1)
CHECKEOF
        log "Playwright MCP already configured in claude.json."
        return 0
    fi

    log "Configuring Playwright MCP server in claude.json..."
    "${VENV_PYTHON}" - "${claude_json}" "${BROWSER_CACHE}" <<'PYEOF'
import json, sys

claude_json_path = sys.argv[1]
browser_cache = sys.argv[2]

try:
    with open(claude_json_path) as f:
        data = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    data = {}

if "mcpServers" not in data:
    data["mcpServers"] = {}

data["mcpServers"]["playwright"] = {
    "command": "npx",
    "args": ["-y", "@playwright/mcp@latest", "--browser", "chromium", "--headless"],
    "env": {
        "PLAYWRIGHT_BROWSERS_PATH": browser_cache,
        "PLAYWRIGHT_MCP_NO_SANDBOX": "true"
    }
}

import tempfile
fd, tmp = tempfile.mkstemp(dir=str(__import__('pathlib').Path(claude_json_path).parent), prefix='.claude.json.', suffix='.tmp')
with __import__('os').fdopen(fd, 'w') as f:
    json.dump(data, f, indent=2)
    f.write("\n")
__import__('os').chmod(tmp, 0o600)
__import__('os').replace(tmp, claude_json_path)
PYEOF

    chown "${REAL_USER}:${REAL_USER}" "$claude_json"
    log "Playwright MCP server configured."
}

# ---------------------------------------------------------------------------
# 6. Verification
# ---------------------------------------------------------------------------
verify_installation() {
    export PLAYWRIGHT_BROWSERS_PATH="$BROWSER_CACHE"

    log "Verifying installation..."
    if sudo -u "$REAL_USER" \
        PLAYWRIGHT_BROWSERS_PATH="$BROWSER_CACHE" \
        "${VENV_PYTHON}" -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('data:text/html,<h1>Arasul Browser OK</h1>')
    title = page.content()
    browser.close()
    assert 'Arasul Browser OK' in title
print('OK')
" 2>/dev/null; then
        log "Headless Chromium is working correctly."
    else
        err "Verification failed. Try manually:"
        err "  PLAYWRIGHT_BROWSERS_PATH=${BROWSER_CACHE} ${VENV_PYTHON} -m playwright install chromium --with-deps"
        exit 1
    fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
echo ""
echo "╔═══════════════════════════════════════════════╗"
echo "║  08 — Headless Browser Setup                  ║"
echo "║  Playwright + Chromium for AI Agents           ║"
echo "╚═══════════════════════════════════════════════╝"
echo ""

install_system_deps
install_playwright_package
setup_browser_cache
install_chromium
setup_mcp_config
verify_installation

echo ""
log "Browser setup complete."
log "  Cache: ${BROWSER_CACHE}"
log "  MCP:   Playwright MCP server in ~/.claude.json"
log "  Test:  /browser status (in Arasul TUI)"
echo ""
