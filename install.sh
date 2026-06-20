#!/usr/bin/env bash
# ============================================================
# Open Ara — One-Command Client Install
#
# Usage (non-interactive, recommended for university IT):
#   bash install.sh --server http://jetson.uni.de:11434/v1
#   bash install.sh --server http://jetson.uni.de:11434/v1 --key SEAT-001
#
# SSH-Tunnel mode (when Ollama port is not directly exposed):
#   bash install.sh --ssh user@jetson.uni.edu
#   bash install.sh --ssh user@jetson.uni.edu --ollama 172.30.0.78:11434
#
# Interactive (prompts for everything):
#   bash install.sh
#
# One-liner from GitHub:
#   curl -sL https://raw.githubusercontent.com/koljaschoepe/OpenAra/main/install.sh | bash -s -- --server URL
# ============================================================
set -euo pipefail

# ── Colours ──────────────────────────────────────────────────
if [[ -t 1 ]]; then
  BOLD="\033[1m"; DIM="\033[2m"; GREEN="\033[32m"; YELLOW="\033[33m"; RED="\033[31m"; RESET="\033[0m"
else
  BOLD=""; DIM=""; GREEN=""; YELLOW=""; RED=""; RESET=""
fi
ok()   { echo -e "  ${GREEN}✓${RESET}  $*"; }
warn() { echo -e "  ${YELLOW}!${RESET}  $*"; }
err()  { echo -e "  ${RED}✗${RESET}  $*"; }
info() { echo -e "  ${DIM}$*${RESET}"; }
h()    { echo -e "\n${BOLD}$*${RESET}"; }

# ── Parse args ───────────────────────────────────────────────
SERVER_URL=""
SSH_HOST=""
OLLAMA_HOST="172.30.0.78"
OLLAMA_PORT=11434
LICENSE_KEY=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --server|-s)  SERVER_URL="$2"; shift 2 ;;
    --key|-k)     LICENSE_KEY="$2"; shift 2 ;;
    --ssh)        SSH_HOST="$2"; shift 2 ;;
    --ollama)     IFS=: read -r OLLAMA_HOST OLLAMA_PORT <<< "$2"; shift 2 ;;
    -h|--help)    sed -n '3,13p' "$0" | sed 's/^# \?//'; exit 0 ;;
    *)            err "Unknown option: $1"; exit 1 ;;
  esac
done

# ── Header ───────────────────────────────────────────────────
echo ""
echo -e "  ${BOLD}Open Ara${RESET} — local AI coding assistant"
echo ""

# ── Check Python ─────────────────────────────────────────────
h "Checking requirements"
if ! command -v python3 &>/dev/null; then
  err "Python 3 not found. Install: https://python.org/downloads"
  exit 1
fi
PY_MAJOR=$(python3 -c "import sys; print(sys.version_info.major)")
PY_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")
PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
if [[ $PY_MAJOR -lt 3 || ($PY_MAJOR -eq 3 && $PY_MINOR -lt 10) ]]; then
  err "Python 3.10+ required (found $PY_VER)"
  exit 1
fi
ok "Python $PY_VER"

# ── Install package ──────────────────────────────────────────
h "Installing Open Ara"
REPO="git+https://github.com/koljaschoepe/OpenAra.git"
PKG="openara[agent] @ ${REPO}"

_install_pkg() {
  # 1. pipx (cleanest on macOS — isolated venv, no PATH issues)
  if command -v pipx &>/dev/null; then
    info "Using pipx…"
    pipx install --force "openara @ ${REPO}" \
      --pip-args "--extra-index-url https://pypi.org/simple/" 2>/dev/null || \
    pipx install --force "openara @ ${REPO}" 2>/dev/null || return 1
    # inject openai separately (pipx extras are tricky with direct URLs)
    pipx inject openara openai 2>/dev/null || true
    return 0
  fi

  # 2. pip --user (works everywhere; bypasses macOS PEP 668 guard)
  if python3 -m pip install --user -q "${PKG}" 2>/dev/null; then
    return 0
  fi

  # 3. pip --user --break-system-packages (macOS Homebrew Python 3.12+)
  if python3 -m pip install --user --break-system-packages -q "${PKG}" 2>/dev/null; then
    return 0
  fi

  return 1
}

if python3 -c "import arasul_tui" 2>/dev/null; then
  ok "openara already installed (dev mode)"
elif _install_pkg; then
  ok "openara installed  (commands: ara · openara · arasul)"
else
  err "Install failed."
  info "Try manually: pip install --user --break-system-packages '${PKG}'"
  info "Or:          brew install pipx && pipx install 'openara @ ${REPO}'"
  exit 1
fi

# ── Ensure ~/.local/bin is in PATH ───────────────────────────
_LOCAL_BIN="$HOME/.local/bin"
if [[ ":$PATH:" != *":${_LOCAL_BIN}:"* ]]; then
  SHELL_RC=""
  if [[ "$SHELL" == *zsh* ]]; then SHELL_RC="$HOME/.zshrc"
  elif [[ "$SHELL" == *bash* ]]; then SHELL_RC="$HOME/.bashrc"; fi

  if [[ -n "$SHELL_RC" ]]; then
    echo "" >> "$SHELL_RC"
    echo "export PATH=\"\$HOME/.local/bin:\$PATH\"  # added by Open Ara install" >> "$SHELL_RC"
    export PATH="${_LOCAL_BIN}:${PATH}"
    warn "Added ~/.local/bin to PATH in ${SHELL_RC} — restart your terminal or run: source ${SHELL_RC}"
  fi
fi

# ── Interactive prompts (if args not provided) ───────────────
if [[ -z "$SERVER_URL" && -z "$SSH_HOST" ]]; then
  h "Server configuration"
  echo ""
  echo -e "  Enter the URL of your Ollama server."
  echo -e "  ${DIM}Examples:${RESET}"
  echo -e "  ${DIM}  http://192.168.1.100:11434/v1${RESET}"
  echo -e "  ${DIM}  http://jetson.local:11434/v1${RESET}"
  echo -e "  ${DIM}  http://jetson.uni-example.de:11434/v1${RESET}"
  echo ""
  read -rp "  Ollama URL: " SERVER_URL
  echo ""
  read -rp "  License key (optional — press Enter to skip): " LICENSE_KEY
fi

# ── Determine connection type & agent URL ────────────────────
if [[ -n "$SSH_HOST" ]]; then
  CONNECTION_TYPE="ssh"
  AGENT_URL="http://localhost:${OLLAMA_PORT}/v1"
else
  CONNECTION_TYPE="direct"
  AGENT_URL="$SERVER_URL"
fi

# ── Save config ──────────────────────────────────────────────
h "Saving configuration"

python3 - <<PYEOF
import json, os, sys

cfg_dir = os.path.expanduser("~/.config/arasul")
os.makedirs(cfg_dir, exist_ok=True)
cfg_file = os.path.join(cfg_dir, "config.json")

try:
    with open(cfg_file) as f:
        data = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    data = {}

data.setdefault("agent", {})["base_url"] = "${AGENT_URL}"

data["install"] = {
    "connection_type": "${CONNECTION_TYPE}",
    "ssh_host":        "${SSH_HOST}",
    "ollama_host":     "${OLLAMA_HOST}",
    "ollama_port":     int("${OLLAMA_PORT}"),
    "license_key":     "${LICENSE_KEY}",
}

with open(cfg_file, "w") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
os.chmod(cfg_file, 0o600)

# Skip name-prompt onboarding (server already configured by IT)
open(os.path.join(cfg_dir, ".onboarded"), "w").close()
PYEOF

ok "Config saved → ~/.config/arasul/config.json"
[[ "$CONNECTION_TYPE" == "ssh" ]] && info "SSH tunnel: ${SSH_HOST} → ${OLLAMA_HOST}:${OLLAMA_PORT} (auto-started by ara)" \
                                  || info "Direct:     ${AGENT_URL}"
[[ -n "$LICENSE_KEY" ]] && info "License:    ${LICENSE_KEY}"

# ── Test connection ───────────────────────────────────────────
h "Testing connection"

if [[ "$CONNECTION_TYPE" == "ssh" ]]; then
  echo -e "  ${DIM}Opening SSH tunnel ${SSH_HOST} → localhost:${OLLAMA_PORT}…${RESET}"
  if ssh -f -N \
       -o ExitOnForwardFailure=yes \
       -o ConnectTimeout=10 \
       -o StrictHostKeyChecking=accept-new \
       -L "${OLLAMA_PORT}:${OLLAMA_HOST}:${OLLAMA_PORT}" \
       "$SSH_HOST" 2>/dev/null; then
    sleep 1  # wait for port to open
    ok "SSH tunnel established"
  else
    warn "SSH tunnel failed — make sure your public key is on ${SSH_HOST}"
    warn "Fix: ssh-copy-id ${SSH_HOST}    then re-run: bash install.sh --ssh ${SSH_HOST}"
    echo ""
    echo -e "  ${BOLD}Open Ara installed${RESET} — fix SSH access then run: ${BOLD}ara agent check${RESET}"
    echo ""
    exit 0
  fi
fi

python3 - <<PYEOF
import asyncio, sys
async def main():
    try:
        from arasul_tui.agent.llm import check_connection
        r = await check_connection("${AGENT_URL}", timeout=8.0)
        if r["ok"]:
            models = "  ·  ".join(r["models"][:4])
            print(f"  \033[32m✓\033[0m  Connected ({r['latency_ms']}ms)")
            print(f"     Models available: {models}")
        else:
            print(f"  \033[33m!\033[0m  {r['error']}", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"  \033[31m✗\033[0m  {e}", file=sys.stderr)
        sys.exit(1)
asyncio.run(main())
PYEOF
CONN_OK=$?

# ── Done ─────────────────────────────────────────────────────
echo ""
echo -e "  ${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo ""
if [[ $CONN_OK -eq 0 ]]; then
  echo -e "  ${GREEN}${BOLD}Ready!${RESET}  Type ${BOLD}ara${RESET} in any project folder to start."
else
  echo -e "  ${YELLOW}Installed${RESET} — run ${BOLD}ara agent check${RESET} once the server is reachable."
fi
echo ""
