"""SSH tunnel management for Open Ara.

When install config specifies connection_type='ssh', an SSH tunnel is
automatically started before the TUI launches, forwarding
localhost:<port> → <ollama_host>:<port> via <ssh_host>.
"""

from __future__ import annotations

import socket
import subprocess
import time


def _port_open(port: int, timeout: float = 1.0) -> bool:
    """Return True if localhost:<port> accepts connections."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def ensure_ssh_tunnel(
    ssh_host: str,
    ollama_host: str,
    ollama_port: int,
    *,
    wait: float = 2.0,
) -> tuple[bool, str]:
    """Start SSH tunnel if not already running.

    Returns (success, message).
    Does nothing if tunnel is already up (port already open).
    """
    if not ssh_host:
        return False, "No SSH host configured"

    if _port_open(ollama_port):
        return True, f"Tunnel already up on localhost:{ollama_port}"

    try:
        subprocess.Popen(
            [
                "ssh",
                "-f",          # fork to background after auth
                "-N",          # no remote command
                "-o", "ExitOnForwardFailure=yes",
                "-o", "ConnectTimeout=10",
                "-o", "StrictHostKeyChecking=accept-new",
                "-o", "BatchMode=yes",  # fail fast if key not set up
                "-L", f"{ollama_port}:{ollama_host}:{ollama_port}",
                ssh_host,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).wait()  # ssh -f forks quickly, wait() returns once forked
    except FileNotFoundError:
        return False, "ssh not found — install OpenSSH"
    except Exception as exc:
        return False, str(exc)

    # Wait up to `wait` seconds for the port to open
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        if _port_open(ollama_port, timeout=0.3):
            return True, f"SSH tunnel → {ssh_host}"
        time.sleep(0.2)

    return False, f"SSH tunnel started but localhost:{ollama_port} not responding"


def get_install_config() -> dict:
    """Load the install section from ~/.config/arasul/config.json."""
    import json
    from pathlib import Path

    cfg_file = Path.home() / ".config" / "arasul" / "config.json"
    try:
        data = json.loads(cfg_file.read_text(encoding="utf-8"))
        return data.get("install", {})
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
