from __future__ import annotations

import os
import subprocess
from pathlib import Path

from arasul_tui.core.claude_json import load_claude_json, save_claude_json
from arasul_tui.core.shell import run_cmd

FALLBACK_BROWSER_CACHE = Path.home() / ".cache" / "ms-playwright"


def _storage_browser_cache() -> Path:
    from arasul_tui.core.platform import get_platform

    p = get_platform()
    if p.storage.is_external:
        return p.storage.mount / "playwright-browsers"
    return FALLBACK_BROWSER_CACHE


def _browsers_path() -> Path:
    env = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if env:
        return Path(env)
    cache = _storage_browser_cache()
    if cache.exists():
        return cache
    return FALLBACK_BROWSER_CACHE


def _find_chromium_binary() -> Path | None:
    base = _browsers_path()
    if not base.exists():
        return None
    for candidate in base.rglob("chrome"):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    for candidate in base.rglob("chromium"):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def is_playwright_installed() -> bool:
    try:
        import playwright  # noqa: F401

        return True
    except ImportError:
        return False


def is_chromium_installed() -> bool:
    return _find_chromium_binary() is not None


def ensure_browser() -> tuple[bool, str]:
    """Check if headless browser stack is ready. Returns (ok, message)."""
    if not is_playwright_installed():
        return False, "Playwright not installed. Run: pip install arasul[browser]"
    if not is_chromium_installed():
        return False, "Chromium not found. Run /browser install."
    return True, "Playwright + Chromium ready."


def browser_health() -> list[tuple[str, str]]:
    """Detailed health check, returns key-value pairs for styled panel."""
    rows: list[tuple[str, str]] = []

    pw_ok = is_playwright_installed()
    if pw_ok:
        try:
            import playwright

            rows.append(("Playwright", f"[green]\u2713[/green] v{playwright.__version__}"))
        except (ImportError, AttributeError):
            rows.append(("Playwright", "[green]\u2713[/green] installed"))
    else:
        rows.append(("Playwright", "[red]not installed[/red]"))

    chrome_bin = _find_chromium_binary()
    if chrome_bin:
        rows.append(("Chromium", "[green]\u2713[/green] installed"))
    else:
        rows.append(("Chromium", "[red]not found[/red]"))

    cache = _browsers_path()
    rows.append(("Cache", f"[dim]{cache}[/dim]"))
    if cache.exists():
        try:
            size_mb = sum(f.stat().st_size for f in cache.rglob("*") if f.is_file()) / (1024 * 1024)
            rows.append(("Cache size", f"{size_mb:.0f} MB"))
        except OSError:
            pass

    mcp_ok = is_mcp_configured()
    rows.append(("MCP Server", "[green]\u2713[/green] configured" if mcp_ok else "[dim]not configured[/dim]"))

    return rows


def browser_test() -> tuple[bool, list[str]]:
    """Launch headless Chromium and load a test page. Returns (ok, lines)."""
    ok, msg = ensure_browser()
    if not ok:
        return False, [msg]

    try:
        env = os.environ.copy()
        env["PLAYWRIGHT_BROWSERS_PATH"] = str(_browsers_path())
        result = subprocess.run(
            [
                "python3",
                "-c",
                "from playwright.sync_api import sync_playwright\n"
                "with sync_playwright() as p:\n"
                "    b = p.chromium.launch(headless=True)\n"
                "    pg = b.new_page()\n"
                "    pg.goto('https://httpbin.org/get', timeout=10000)\n"
                "    status = pg.title()\n"
                "    b.close()\n"
                "    print('OK')\n",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        if result.returncode == 0 and "OK" in result.stdout:
            return True, ["Browser test successful: Chromium headless is running."]
        stderr = result.stderr.strip()[:200] if result.stderr else "unknown error"
        return False, [f"Browser test failed: {stderr}"]
    except subprocess.TimeoutExpired:
        return False, ["Browser test timeout (30s). Network or Chromium issue."]
    except OSError as exc:
        return False, [f"Browser test error: {exc}"]


def install_browser() -> tuple[bool, list[str]]:
    """Install/update Playwright + Chromium. Requires system packages pre-installed."""
    lines: list[str] = []

    if not is_playwright_installed():
        lines.append("Installing Playwright...")
        result = subprocess.run(
            ["pip3", "install", "playwright"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            return False, lines + [f"pip install playwright failed: {result.stderr[:200]}"]
        lines.append("Playwright installed.")

    cache = _browsers_path()
    lines.append(f"Downloading Chromium to {cache}...")
    env = os.environ.copy()
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(cache)
    result = subprocess.run(
        ["python3", "-m", "playwright", "install", "chromium"],
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
    )
    if result.returncode != 0:
        return False, lines + [f"Chromium download failed: {result.stderr[:200]}"]
    lines.append("Chromium downloaded.")

    return True, lines


def is_mcp_configured() -> bool:
    """Check if Playwright MCP server is configured in claude.json."""
    data = load_claude_json()
    return "playwright" in data.get("mcpServers", {})


def configure_mcp() -> tuple[bool, str]:
    """Add Playwright MCP server to claude.json."""
    npx_path = run_cmd("command -v npx 2>/dev/null", timeout=2)
    if not npx_path or npx_path.startswith("Error"):
        return False, "Node.js/npx not installed. Run: /setup (Step 6)"

    data = load_claude_json()

    if "mcpServers" not in data:
        data["mcpServers"] = {}

    data["mcpServers"]["playwright"] = {
        "command": "npx",
        "args": ["-y", "@playwright/mcp@latest", "--browser", "chromium", "--headless"],
        "env": {
            "PLAYWRIGHT_BROWSERS_PATH": str(_browsers_path()),
            "PLAYWRIGHT_MCP_NO_SANDBOX": "true",
        },
    }

    save_claude_json(data)
    return True, "Playwright MCP server configured in ~/.claude.json."
