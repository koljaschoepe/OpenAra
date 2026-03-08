#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_DIR="${HOME}/venvs/arasul"

echo "[arasul] Creating venv: ${VENV_DIR}"
python3 -m venv "${VENV_DIR}"
# shellcheck disable=SC1090
source "${VENV_DIR}/bin/activate"

echo "[arasul] Installing dependencies..."
python -m pip install --upgrade pip
python -m pip install -e "${REPO_ROOT}"

# Detect storage mount for browser cache
if [[ -f "${REPO_ROOT}/lib/detect.sh" ]]; then
  # shellcheck source=../lib/detect.sh
  source "${REPO_ROOT}/lib/detect.sh"
  STORAGE_MOUNT="$(detect_storage_mount)"
else
  STORAGE_MOUNT="${HOME}"
fi

if [[ -d "${STORAGE_MOUNT}" && "${STORAGE_MOUNT}" != "${HOME}" ]]; then
  BROWSER_CACHE="${STORAGE_MOUNT}/playwright-browsers"
else
  BROWSER_CACHE="${HOME}/.cache/ms-playwright"
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
  RC_FILE="${HOME}/.zshrc"
else
  RC_FILE="${HOME}/.bashrc"
fi

if ! grep -q "PLAYWRIGHT_BROWSERS_PATH" "${RC_FILE}" 2>/dev/null; then
  echo "" >> "${RC_FILE}"
  echo "export PLAYWRIGHT_BROWSERS_PATH=\"${BROWSER_CACHE}\"" >> "${RC_FILE}"
fi

echo "[arasul] Creating launcher: /usr/local/bin/arasul"
sudo tee /usr/local/bin/arasul >/dev/null <<'EOF'
#!/usr/bin/env bash
exec "$HOME/venvs/arasul/bin/arasul" "$@"
EOF
sudo chmod +x /usr/local/bin/arasul

if grep -q "alias atui='arasul-shell'" "${HOME}/.bash_aliases" 2>/dev/null; then
  sed -i "s|alias atui='arasul-shell'|alias atui='arasul'|g" "${HOME}/.bash_aliases"
fi

echo "[arasul] Done. Start with: arasul (or alias: atui)"
