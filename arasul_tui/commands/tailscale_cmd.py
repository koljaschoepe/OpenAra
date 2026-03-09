from __future__ import annotations

import socket

from arasul_tui.core.shell import run_cmd
from arasul_tui.core.state import TuiState
from arasul_tui.core.types import CommandResult
from arasul_tui.core.ui import (
    console,
    content_pad,
    print_error,
    print_info,
    print_styled_panel,
    print_success,
    print_warning,
    spinner_run,
)


def _is_installed() -> bool:
    return bool(run_cmd("command -v tailscale 2>/dev/null", timeout=2))


def _is_connected() -> bool:
    status = run_cmd("tailscale status --json 2>/dev/null", timeout=5)
    if not status or status.startswith("Error"):
        return False
    try:
        import json

        data = json.loads(status)
        # Check BackendState for definitive connected status
        backend = data.get("BackendState", "")
        if backend == "Running":
            return True
        # Fallback: check Self.Online
        self_info = data.get("Self", {})
        return bool(self_info.get("Online", False))
    except (json.JSONDecodeError, TypeError):
        return False


def _tailscale_status_rows() -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []

    if not _is_installed():
        rows.append(("Tailscale", "[dim]not installed[/dim]"))
        return rows

    rows.append(("Installed", "[green]yes[/green]"))

    ip4 = run_cmd("tailscale ip -4 2>/dev/null", timeout=5).strip()
    ip6 = run_cmd("tailscale ip -6 2>/dev/null", timeout=5).strip()
    status_raw = run_cmd("tailscale status 2>/dev/null", timeout=5)

    if ip4:
        rows.append(("Tailscale IP", f"[bold]{ip4}[/bold]"))
        if ip6:
            rows.append(("IPv6", f"[dim]{ip6}[/dim]"))
        rows.append(("Status", "[green]connected[/green]"))

        hostname = socket.gethostname()
        rows.append(("SSH", f"[cyan]ssh {hostname}[/cyan] (via Tailscale)"))

        # Show peers
        peers: list[str] = []
        if status_raw and not status_raw.startswith("Error"):
            for line in status_raw.splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 4:
                    name = parts[1]
                    peer_status = parts[3] if len(parts) > 3 else ""
                    icon = "[green]●[/green]" if peer_status == "active" else "[dim]○[/dim]"
                    peers.append(f"{icon} {name}")
            if peers:
                rows.append(("Peers", peers[0]))
                for p in peers[1:5]:
                    rows.append(("", p))
    else:
        rows.append(("Status", "[yellow]installed but not connected[/yellow]"))
        rows.append(("Connect", "[cyan]sudo tailscale up[/cyan]"))

    return rows


# ---------------------------------------------------------------------------
# /tailscale (no args) — status dashboard
# ---------------------------------------------------------------------------


def _show_status() -> CommandResult:
    rows = _tailscale_status_rows()
    print_styled_panel("Tailscale VPN", rows)
    return CommandResult(ok=True, style="silent")


# ---------------------------------------------------------------------------
# /tailscale install
# ---------------------------------------------------------------------------


def _do_install() -> CommandResult:
    if _is_installed():
        ver = run_cmd("tailscale version 2>/dev/null | head -1", timeout=3)
        print_success(f"Tailscale already installed: [dim]{ver}[/dim]")
        return _show_status()

    def _run_install() -> str:
        return run_cmd("curl -fsSL https://tailscale.com/install.sh | sh 2>&1", timeout=120)

    try:
        spinner_run("Installing Tailscale...", _run_install)
    except OSError as exc:
        print_error(f"Installation failed: {exc}")
        return CommandResult(ok=False, style="silent")

    if not _is_installed():
        print_error("Tailscale binary not found after install.")
        return CommandResult(ok=False, style="silent")

    ver = run_cmd("tailscale version 2>/dev/null | head -1", timeout=3)
    print_success(f"Tailscale installed: [dim]{ver}[/dim]")
    console.print()
    print_info("Next: run [bold]/tailscale up[/bold] to connect.")
    return CommandResult(ok=True, style="silent")


# ---------------------------------------------------------------------------
# /tailscale up
# ---------------------------------------------------------------------------


def _do_up() -> CommandResult:
    if not _is_installed():
        print_warning("Tailscale not installed. Run [bold]/tailscale install[/bold] first.")
        return CommandResult(ok=False, style="silent")

    if _is_connected():
        ip = run_cmd("tailscale ip -4 2>/dev/null", timeout=5).strip()
        print_success(f"Already connected: [bold]{ip}[/bold]")
        return _show_status()

    pad = content_pad()
    print_info("Starting Tailscale authentication...")
    console.print()

    # tailscale up blocks until the user authenticates via a URL.
    # We run it in the background and poll for the auth URL or connection.
    import subprocess
    import time

    proc = subprocess.Popen(
        ["sudo", "tailscale", "up"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
    )

    auth_url = None
    # Poll for up to 10 seconds to capture the auth URL from stdout
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            break
        import select

        ready, _, _ = select.select([proc.stdout], [], [], 0.5)
        if ready:
            line = proc.stdout.readline()
            if line and "https://" in line:
                for part in line.split():
                    if part.startswith("https://"):
                        auth_url = part
                        break
                if auth_url:
                    break

    if auth_url:
        console.print(f"{pad}[bold cyan]{auth_url}[/bold cyan]", highlight=False)
        console.print()
        print_info("Open this URL in your browser to authenticate.")
        print_info("Then type [bold]/tailscale[/bold] to check status.")
        # Don't wait for the process — it will complete when user authenticates
    elif _is_connected():
        ip = run_cmd("tailscale ip -4 2>/dev/null", timeout=5).strip()
        print_success(f"Connected: [bold]{ip}[/bold]")
    else:
        print_warning("Tailscale started but may need authentication.")
        print_info("Run [bold]sudo tailscale up[/bold] in a terminal to see the auth URL.")

    return CommandResult(ok=True, style="silent")


# ---------------------------------------------------------------------------
# /tailscale down
# ---------------------------------------------------------------------------


def _do_down() -> CommandResult:
    if not _is_installed():
        print_warning("Tailscale not installed.")
        return CommandResult(ok=False, style="silent")

    if not _is_connected():
        print_info("Tailscale is already disconnected.")
        return CommandResult(ok=True, style="silent")

    output = run_cmd("sudo tailscale down 2>&1", timeout=10)
    if output and ("error" in output.lower() or "denied" in output.lower()):
        print_error(f"Disconnect failed: {output[:200]}")
        return CommandResult(ok=False, style="silent")
    print_success("Tailscale disconnected.")
    return CommandResult(ok=True, style="silent")


# ---------------------------------------------------------------------------
# /tailscale (dispatcher)
# ---------------------------------------------------------------------------


def cmd_tailscale(state: TuiState, args: list[str]) -> CommandResult:
    if not args:
        return _show_status()

    sub = args[0].lower()

    if sub == "install":
        return _do_install()

    if sub == "up":
        return _do_up()

    if sub == "down":
        return _do_down()

    if sub == "status":
        return _show_status()

    print_error(f"Unknown: [bold]/tailscale {sub}[/bold]")
    print_info("Available: [bold]status[/bold], [bold]install[/bold], [bold]up[/bold], [bold]down[/bold]")
    return CommandResult(ok=False, style="silent")
