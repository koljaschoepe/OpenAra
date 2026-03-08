"""n8n workflow automation — /n8n command handler.

Smart command that does the right thing based on current state:
- Not installed  -> install + start + guide through API key + MCP
- Stopped        -> start
- No API key     -> prompt for key + configure MCP
- All good       -> show status dashboard

Only subcommand: /n8n stop
"""

from __future__ import annotations

import os
import shlex
from pathlib import Path

from arasul_tui.core.n8n_client import (
    N8N_BASE_URL,
    n8n_compose_cmd,
    n8n_dir,
    n8n_get_api_key,
    n8n_health,
    n8n_is_installed,
    n8n_is_running,
    n8n_list_workflows,
    n8n_save_api_key,
)
from arasul_tui.core.n8n_mcp import (
    configure_n8n_mcp,
    is_n8n_mcp_configured,
)
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
from arasul_tui.core.ui.animated_install import run_install_animated

# ---------------------------------------------------------------------------
# Animated install: step definitions + milestone checks
# ---------------------------------------------------------------------------


def _check_milestone(index: int) -> bool:
    """Check if a milestone is reached by polling filesystem/docker."""
    d = n8n_dir()
    if index == 0:  # Directories
        return d.is_dir()
    if index == 1:  # Environment
        return (d / ".env").is_file()
    if index == 2:  # Compose file
        return (d / "docker-compose.yml").is_file()
    if index == 3:  # Images pulled (containers exist, even if not running yet)
        out = run_cmd(
            "docker images --format '{{.Repository}}' 2>/dev/null | grep -c n8n",
            timeout=5,
        )
        return bool(out and out.strip().isdigit() and int(out.strip()) > 0)
    if index == 4:  # Containers running
        return n8n_is_running()
    if index == 5:  # Health check (8s timeout for slow ARM devices)
        try:
            from urllib.request import Request, urlopen

            req = Request(f"{N8N_BASE_URL}/healthz", method="GET")
            with urlopen(req, timeout=8) as resp:
                return resp.status == 200
        except (OSError, ValueError):
            return False
    return False


def _steps() -> list[tuple[str, str]]:
    return [
        ("Directories", str(n8n_dir())),
        ("Environment", "credentials + encryption key"),
        ("Compose file", "n8n + PostgreSQL stack"),
        ("Pulling images", "this may take a few minutes"),
        ("Starting containers", "n8n + PostgreSQL"),
        ("Health check", "waiting for API"),
    ]


# ---------------------------------------------------------------------------
# Status dashboard
# ---------------------------------------------------------------------------


def _show_status() -> CommandResult:
    rows: list[tuple[str, str]] = []

    health = n8n_health()

    # Container status
    container = health.get("container", "not found")
    if "Up" in container:
        rows.append(("n8n", f"[green]running[/green] [dim]({container})[/dim]"))
    else:
        rows.append(("n8n", f"[yellow]{container}[/yellow]"))

    # Postgres
    pg = health.get("postgres", "not found")
    if "Up" in pg:
        rows.append(("PostgreSQL", "[green]running[/green]"))
    else:
        rows.append(("PostgreSQL", f"[yellow]{pg}[/yellow]"))

    # API
    api = health.get("api", "unreachable")
    if api == "healthy":
        rows.append(("API", "[green]healthy[/green]"))
    else:
        rows.append(("API", f"[yellow]{api}[/yellow]"))

    # API key
    api_key = n8n_get_api_key()
    if api_key:
        rows.append(("API Key", f"[green]configured[/green] [dim]({api_key[:8]}...)[/dim]"))
    else:
        rows.append(("API Key", "[dim]not set[/dim]"))

    # Workflows (only if API key is set and n8n is running)
    if api_key and api == "healthy":
        workflows = n8n_list_workflows()
        active = sum(1 for w in workflows if w.get("active"))
        rows.append(("Workflows", f"{len(workflows)} total, {active} active"))

    # MCP server
    if is_n8n_mcp_configured():
        rows.append(("MCP Server", "[green]configured[/green]"))
    else:
        rows.append(("MCP Server", "[dim]not set[/dim]"))

    # URLs + access info
    from arasul_tui.core.n8n_client import n8n_access_info

    access = n8n_access_info()
    rows.append(("Web UI", f"[cyan]{N8N_BASE_URL}[/cyan]"))
    if access.tailscale_url:
        rows.append(("Tailscale", f"[cyan]{access.tailscale_url}[/cyan]"))
    rows.append(("SSH Tunnel", f"[dim]{access.ssh_tunnel_cmd}[/dim]"))
    rows.append(("Data", f"[dim]{n8n_dir()}[/dim]"))

    print_styled_panel("n8n Automation", rows)
    return CommandResult(ok=True, style="silent")


# ---------------------------------------------------------------------------
# Smart flow: install -> start -> api-key -> mcp
# ---------------------------------------------------------------------------


def _smart_flow(state: TuiState) -> CommandResult:
    # --- Pre-check: Docker daemon ---
    docker_check = run_cmd("docker info 2>/dev/null", timeout=5)
    if not docker_check or docker_check.startswith("Error") or "Cannot connect" in docker_check:
        print_error("Docker is not running.")
        print_info("Start it: [bold]sudo systemctl start docker[/bold]")
        print_info("Or install: [bold]/setup[/bold] → Step 5")
        return CommandResult(ok=False, style="silent")

    # --- Step 1: Install if needed ---
    if not n8n_is_installed():
        script = run_cmd("command -v sudo 2>/dev/null", timeout=2)
        if not script:
            print_error("sudo not available.")
            return CommandResult(ok=False, style="silent")

        # Resolve absolute path to setup script
        repo_root = Path(__file__).parent.parent.parent
        setup_script = repo_root / "scripts" / "09-n8n-setup.sh"
        if not setup_script.exists():
            print_error(f"Setup script not found: {setup_script}")
            return CommandResult(ok=False, style="silent")

        # The script needs STORAGE_MOUNT, REAL_USER, and SCRIPT_DIR
        from arasul_tui.core.platform import get_platform

        mount = get_platform().storage.mount
        real_user = os.environ.get("USER") or os.environ.get("LOGNAME", "")
        env_vars = (
            f"STORAGE_MOUNT={shlex.quote(str(mount))}"
            f" NVME_MOUNT={shlex.quote(str(mount))}"
            f" REAL_USER={shlex.quote(real_user)}"
            f" SCRIPT_DIR={shlex.quote(str(repo_root))}"
        )

        console.print()
        try:
            ok, output = run_install_animated(
                f"sudo {env_vars} bash {shlex.quote(str(setup_script))} 2>&1",
                title="n8n Setup",
                steps=_steps(),
                check_milestone=_check_milestone,
                is_success=n8n_is_running,
            )
        except OSError as exc:
            print_error(f"Installation failed: {exc}")
            return CommandResult(ok=False, style="silent")

        if not ok:
            print_warning("n8n is not running after install.")
            if output:
                pad = content_pad()
                console.print(f"{pad}[dim]{output[-500:]}[/dim]", highlight=False)
            print_info("Try again: [bold]/n8n[/bold] or check [dim]/var/log/arasul/[/dim]")
            return CommandResult(ok=False, style="silent")

        console.print()
        print_success("n8n installed and running!")

    # --- Step 2: Start if stopped ---
    if n8n_is_installed() and not n8n_is_running():

        def _run_start() -> str:
            return n8n_compose_cmd("up -d")

        spinner_run("Starting n8n...", _run_start)

        if not n8n_is_running():
            print_error("n8n failed to start.")
            print_info("Check logs: [bold]docker compose -f ~/n8n/docker-compose.yml logs[/bold]")
            return CommandResult(ok=False, style="silent")

        print_success(f"n8n started at [bold]{N8N_BASE_URL}[/bold]")

    # --- Step 3: API key if missing ---
    api_key = n8n_get_api_key()
    if not api_key:
        console.print()
        import socket

        hostname = socket.gethostname()
        print_info("From your Mac:")
        print_info(f"  [bold]ssh -L 5678:localhost:5678 {hostname}[/bold]")
        print_info(f"Then open [bold cyan]{N8N_BASE_URL}/settings/api[/bold cyan]")
        print_info("and create an API key.")
        return CommandResult(
            ok=True,
            style="silent",
            prompt="Paste API key",
            pending_handler=_api_key_finish,
            wizard_step=(1, 1, "API Key"),
        )

    # --- Step 4: MCP if not configured ---
    if not is_n8n_mcp_configured():
        ok, msg = configure_n8n_mcp(api_key)
        if ok:
            print_success("MCP server configured.")
        else:
            print_warning(f"MCP setup failed: {msg}")

    # --- Step 5: Ensure n8n-workflows project exists ---
    project_created = _ensure_n8n_project(state)

    # --- All good: show status ---
    result = _show_status()
    if project_created:
        result.refresh = True
    return result


def _api_key_finish(state: TuiState, raw: str) -> CommandResult:
    key = raw.strip()
    if not key:
        print_error("No key provided.")
        return CommandResult(ok=False, style="silent")

    try:
        n8n_save_api_key(key)
    except OSError as exc:
        print_error(f"Failed to save API key: {exc}")
        return CommandResult(ok=False, style="silent")
    print_success(f"API key saved: [dim]{key[:8]}...[/dim]")

    # Auto-configure MCP after saving API key
    if not is_n8n_mcp_configured():
        ok, msg = configure_n8n_mcp(key)
        if ok:
            print_success("MCP server configured.")
        else:
            print_warning(f"MCP setup failed: {msg}")

    # Create n8n-workflows project
    _ensure_n8n_project(state)

    print_success("n8n is ready! Open [bold]n8n-workflows[/bold] to start building workflows.")
    return CommandResult(ok=True, style="silent", refresh=True)


# ---------------------------------------------------------------------------
# Auto-create n8n-workflows project
# ---------------------------------------------------------------------------


def _ensure_n8n_project(state: TuiState) -> bool:
    """Create the n8n-workflows project if it doesn't exist yet.

    Returns True if a new project was created (caller should refresh).
    """
    from arasul_tui.core.n8n_project import scaffold_n8n_project
    from arasul_tui.core.projects import get_project, register_project

    project_dir = state.project_root / "n8n-workflows"

    # Already registered and exists on disk?
    existing = get_project("n8n-workflows")
    if existing and Path(existing.path).is_dir():
        return False

    created = False

    # Create directory + scaffold
    if not project_dir.exists():
        project_dir.mkdir(parents=True, exist_ok=True)
        scaffold_n8n_project(project_dir)
        print_success("Project [bold]n8n-workflows[/bold] created.")
        print_info("CLAUDE.md and guardrails configured.")
        created = True

    # Register in project list
    if not existing:
        register_project(name="n8n-workflows", path=project_dir, provider_default="claude")
        created = True

    return created


# ---------------------------------------------------------------------------
# /n8n stop
# ---------------------------------------------------------------------------


def _do_stop() -> CommandResult:
    if not n8n_is_installed():
        print_warning("n8n not installed.")
        return CommandResult(ok=False, style="silent")

    if not n8n_is_running():
        print_info("n8n is already stopped.")
        return CommandResult(ok=True, style="silent")

    def _run_stop() -> str:
        return n8n_compose_cmd("down")

    spinner_run("Stopping n8n...", _run_stop)
    print_success("n8n stopped.")
    return CommandResult(ok=True, style="silent")


# ---------------------------------------------------------------------------
# /n8n (dispatcher)
# ---------------------------------------------------------------------------


def cmd_n8n(state: TuiState, args: list[str]) -> CommandResult:
    if args and args[0].lower() == "stop":
        return _do_stop()

    return _smart_flow(state)
