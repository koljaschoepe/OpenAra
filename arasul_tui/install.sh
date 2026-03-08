#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Resolve actual user when run via sudo
REAL_USER="${SUDO_USER:-$(whoami)}"
REAL_HOME=$(eval echo "~${REAL_USER}")
VENV_DIR="${REAL_HOME}/venvs/arasul"

# Validate Python version (3.10+ required)
PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "0.0")
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
if [[ "$PY_MAJOR" -lt 3 ]] || { [[ "$PY_MAJOR" -eq 3 ]] && [[ "$PY_MINOR" -lt 10 ]]; }; then
  echo "[arasul] ERROR: Python 3.10+ required, but found Python ${PY_VERSION}"
  echo "[arasul] Install: sudo apt-get install python3.11 python3.11-venv"
  exit 1
fi

echo "[arasul] Creating venv: ${VENV_DIR}"
python3 -m venv "${VENV_DIR}"
# shellcheck disable=SC1090
source "${VENV_DIR}/bin/activate"

echo "[arasul] Installing dependencies..."
if ! python -m pip install --upgrade pip; then
  echo "[arasul] ERROR: Failed to upgrade pip. Check disk space and permissions."
  exit 1
fi
if ! python -m pip install -e "${REPO_ROOT}"; then
  echo "[arasul] ERROR: Failed to install arasul package."
  exit 1
fi

# Detect storage mount for browser cache
if [[ -f "${REPO_ROOT}/lib/detect.sh" ]]; then
  # shellcheck source=../lib/detect.sh
  source "${REPO_ROOT}/lib/detect.sh"
  STORAGE_MOUNT="$(detect_storage_mount)"
else
  STORAGE_MOUNT="${REAL_HOME}"
fi

if [[ -d "${STORAGE_MOUNT}" && "${STORAGE_MOUNT}" != "${REAL_HOME}" ]]; then
  BROWSER_CACHE="${STORAGE_MOUNT}/playwright-browsers"
else
  BROWSER_CACHE="${REAL_HOME}/.cache/ms-playwright"
fi

# Install Playwright Chromium only if playwright is available
if python -m playwright --version &>/dev/null; then
  echo "[arasul] Installing Playwright Chromium to ${BROWSER_CACHE}..."
  mkdir -p "${BROWSER_CACHE}"
  PLAYWRIGHT_BROWSERS_PATH="${BROWSER_CACHE}" python -m playwright install chromium 2>/dev/null || \
    echo "[arasul] WARN: Chromium download failed (run /browser install later)"
else
  echo "[arasul] Playwright not installed — skipping Chromium download"
fi

# Detect shell RC file
if [[ "${SHELL}" == *"zsh"* ]]; then
  RC_FILE="${REAL_HOME}/.zshrc"
else
  RC_FILE="${REAL_HOME}/.bashrc"
fi

if ! grep -q "PLAYWRIGHT_BROWSERS_PATH" "${RC_FILE}" 2>/dev/null; then
  echo "" >> "${RC_FILE}"
  echo "export PLAYWRIGHT_BROWSERS_PATH=\"${BROWSER_CACHE}\"" >> "${RC_FILE}"
fi

echo "[arasul] Creating launcher: /usr/local/bin/arasul"
sudo tee /usr/local/bin/arasul >/dev/null <<EOF
#!/usr/bin/env bash
exec "${VENV_DIR}/bin/arasul" "\$@"
EOF
sudo chmod +x /usr/local/bin/arasul

if grep -q "alias atui='arasul-shell'" "${REAL_HOME}/.bash_aliases" 2>/dev/null; then
  sed -i "s|alias atui='arasul-shell'|alias atui='arasul'|g" "${REAL_HOME}/.bash_aliases"
fi

echo "[arasul] Done. Start with: arasul (or alias: atui)"
