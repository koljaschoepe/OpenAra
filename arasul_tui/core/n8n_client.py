"""n8n API client — health checks, workflow listing, API key management."""

from __future__ import annotations

import json
import shlex
import socket
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from arasul_tui.core.shell import run_cmd

N8N_CONFIG = Path.home() / ".config" / "arasul" / "n8n.yaml"


def n8n_dir() -> Path:
    from arasul_tui.core.platform import get_platform

    return get_platform().storage.mount / "n8n"


def _n8n_compose() -> Path:
    return n8n_dir() / "docker-compose.yml"


N8N_BASE_URL = "http://localhost:5678"
API_TIMEOUT = 5


# ---------------------------------------------------------------------------
# Cached status + access info (for project screen)
# ---------------------------------------------------------------------------


@dataclass
class N8nAccessInfo:
    """Access information for reaching n8n web UI from a remote machine."""

    is_running: bool
    hostname: str
    tailscale_url: str
    ssh_tunnel_cmd: str
    local_url: str


def n8n_running_cached(ttl: float = 10.0) -> bool:
    """Check if n8n is running, with result caching."""
    from arasul_tui.core.cache import cached_cmd

    out = cached_cmd(
        "docker ps --filter name=n8n --filter status=running --format '{{.Names}}' 2>/dev/null",
        timeout=5,
        ttl=ttl,
    )
    return bool(out and "n8n" in out and not out.startswith("Error"))


def _tailscale_hostname_cached() -> str:
    """Get the Tailscale DNS name, cached for 60 seconds."""
    from arasul_tui.core.cache import cached_cmd

    raw = cached_cmd("tailscale status --json 2>/dev/null", timeout=5, ttl=60)
    if not raw or raw.startswith("Error"):
        return ""
    try:
        data = json.loads(raw)
        dns = data.get("Self", {}).get("DNSName", "")
        return dns.rstrip(".") if dns else ""
    except (json.JSONDecodeError, KeyError):
        return ""


def n8n_access_info() -> N8nAccessInfo:
    """Gather n8n access information with caching."""
    from arasul_tui.core.cache import cached_cmd, parallel_cmds

    # Run n8n + tailscale checks in parallel
    cmds = {
        "n8n_running": (
            "docker ps --filter name=n8n --filter status=running --format '{{.Names}}' 2>/dev/null",
            5,
        ),
        "ts_installed": ("command -v tailscale 2>/dev/null", 2),
    }
    r = parallel_cmds(cmds)

    n8n_out = r.get("n8n_running", "")
    is_running = bool(n8n_out and "n8n" in n8n_out and not n8n_out.startswith("Error"))

    hostname = socket.gethostname()
    ssh_cmd = f"ssh -L 5678:localhost:5678 {hostname}"

    # Check Tailscale serve status (only if Tailscale is installed)
    ts_url = ""
    ts_installed = r.get("ts_installed", "")
    if ts_installed and not ts_installed.startswith("Error"):
        ts_serve = cached_cmd("tailscale serve status 2>/dev/null", timeout=5, ttl=30)
        if ts_serve and "5678" in ts_serve:
            ts_dns = _tailscale_hostname_cached()
            if ts_dns:
                ts_url = f"https://{ts_dns}"

    return N8nAccessInfo(
        is_running=is_running,
        hostname=hostname,
        tailscale_url=ts_url,
        ssh_tunnel_cmd=ssh_cmd,
        local_url=N8N_BASE_URL,
    )


def n8n_is_installed() -> bool:
    """Check if n8n docker-compose stack exists on disk."""
    return _n8n_compose().exists()


def n8n_is_running() -> bool:
    """Check if n8n container is running."""
    out = run_cmd(
        "docker ps --filter name=n8n --filter status=running --format '{{.Names}}' 2>/dev/null",
        timeout=5,
    )
    return bool(out and "n8n" in out and not out.startswith("Error"))


def n8n_health() -> dict[str, str]:
    """Return n8n health info: container status, API reachable, version."""
    info: dict[str, str] = {}

    # Container status
    status = run_cmd(
        "docker ps --filter name=n8n -a --format '{{.Status}}' 2>/dev/null",
        timeout=5,
    )
    info["container"] = status if status and not status.startswith("Error") else "not found"

    # Postgres status
    pg_status = run_cmd(
        "docker ps --filter name=postgres --filter status=running --format '{{.Status}}' 2>/dev/null",
        timeout=5,
    )
    info["postgres"] = pg_status if pg_status and not pg_status.startswith("Error") else "not found"

    # API health
    try:
        req = Request(f"{N8N_BASE_URL}/healthz", method="GET")
        with urlopen(req, timeout=API_TIMEOUT) as resp:
            info["api"] = "healthy" if resp.status == 200 else f"status {resp.status}"
    except (URLError, OSError):
        info["api"] = "unreachable"

    return info


def n8n_api_request(method: str, endpoint: str, data: dict | None = None, retries: int = 2) -> dict | list | None:
    """Make a REST API call to n8n. Returns parsed JSON or None on failure.

    Retries on transient connection errors (n8n may still be starting).
    """
    api_key = n8n_get_api_key()
    if not api_key:
        return None

    url = f"{N8N_BASE_URL}/api/v1{endpoint}"
    headers = {"X-N8N-API-KEY": api_key, "Content-Type": "application/json"}

    body = json.dumps(data).encode() if data else None

    for attempt in range(1 + retries):
        req = Request(url, data=body, headers=headers, method=method)
        try:
            with urlopen(req, timeout=API_TIMEOUT) as resp:
                return json.loads(resp.read())
        except json.JSONDecodeError:
            return None  # Response received but unparseable — no retry
        except (URLError, OSError):
            if attempt < retries:
                import time

                time.sleep(1)
                continue
            return None


def n8n_list_workflows() -> list[dict]:
    """GET /api/v1/workflows — returns list of workflows or empty list."""
    result = n8n_api_request("GET", "/workflows")
    if isinstance(result, dict) and "data" in result:
        return result["data"]
    if isinstance(result, list):
        return result
    return []


def n8n_list_executions(limit: int = 10) -> list[dict]:
    """GET /api/v1/executions — returns recent executions."""
    result = n8n_api_request("GET", f"/executions?limit={limit}")
    if isinstance(result, dict) and "data" in result:
        return result["data"]
    if isinstance(result, list):
        return result
    return []


def n8n_get_api_key() -> str | None:
    """Read API key from config file."""
    if not N8N_CONFIG.exists():
        return None
    try:
        import yaml

        cfg = yaml.safe_load(N8N_CONFIG.read_text())
        return cfg.get("api_key") if cfg else None
    except Exception:
        # Fallback: simple key=value parsing
        for line in N8N_CONFIG.read_text().splitlines():
            if line.startswith("api_key:"):
                return line.split(":", 1)[1].strip().strip("\"'")
    return None


def n8n_save_api_key(key: str) -> None:
    """Save API key to config file."""
    N8N_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    try:
        import yaml

        cfg: dict = {}
        if N8N_CONFIG.exists():
            cfg = yaml.safe_load(N8N_CONFIG.read_text()) or {}
        cfg["api_key"] = key
        N8N_CONFIG.write_text(yaml.dump(cfg, default_flow_style=False))
    except ImportError:
        # Fallback without yaml
        N8N_CONFIG.write_text(f"api_key: {key}\n")
    N8N_CONFIG.chmod(0o600)


def n8n_compose_cmd(subcmd: str) -> str:
    """Run docker compose command in n8n directory. Returns output."""
    return run_cmd(
        f"docker compose -f {shlex.quote(str(_n8n_compose()))} {subcmd} 2>&1",
        timeout=30,
    )
