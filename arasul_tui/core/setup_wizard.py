from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from arasul_tui.core.shell import run_cmd


@dataclass
class SetupStep:
    number: int
    name: str
    description: str
    script: str
    check_done: Callable[[], bool]


def _service_active(name: str) -> bool:
    out = run_cmd(f"systemctl is-active {name} 2>/dev/null")
    return out == "active"


def _file_exists(path: str) -> bool:
    return Path(path).exists()


def _cmd_exists(cmd: str) -> bool:
    out = run_cmd(f"command -v {cmd} 2>/dev/null")
    return bool(out and not out.startswith("Error"))


SETUP_STEPS: list[SetupStep] = [
    SetupStep(
        number=1,
        name="System Optimize",
        description="Disable GUI, reduce services, tune kernel",
        script="scripts/01-system-optimize.sh",
        check_done=lambda: (
            _file_exists("/etc/sysctl.d/99-arasul-system.conf") or _file_exists("/etc/sysctl.d/99-jetson-dev.conf")
        ),
    ),
    SetupStep(
        number=2,
        name="Network Setup",
        description="Hostname, mDNS, UFW firewall",
        script="scripts/02-network-setup.sh",
        check_done=lambda: _service_active("avahi-daemon"),
    ),
    SetupStep(
        number=3,
        name="SSH Hardening",
        description="Key-only auth, fail2ban",
        script="scripts/03-ssh-harden.sh",
        check_done=lambda: (
            _file_exists("/etc/ssh/sshd_config.d/99-arasul-hardened.conf")
            or _file_exists("/etc/ssh/sshd_config.d/99-jetson-hardened.conf")
        ),
    ),
    SetupStep(
        number=4,
        name="Storage Setup",
        description="Partition, mount, swap, I/O scheduler",
        script="scripts/04-storage-setup.sh",
        check_done=lambda: (
            _file_exists("/mnt/data") or _file_exists("/mnt/nvme") or _file_exists(str(Path.home() / "projects"))
        ),
    ),
    SetupStep(
        number=5,
        name="Docker Setup",
        description="Docker + Compose",
        script="scripts/05-docker-setup.sh",
        check_done=lambda: _cmd_exists("docker"),
    ),
    SetupStep(
        number=6,
        name="Dev Tools",
        description="Node.js, Python, Git, Claude Code",
        script="scripts/06-devtools-setup.sh",
        check_done=lambda: _cmd_exists("node"),
    ),
    SetupStep(
        number=7,
        name="Quality of Life",
        description="tmux, aliases, MOTD",
        script="scripts/07-quality-of-life.sh",
        check_done=lambda: _file_exists(str(Path.home() / ".bash_aliases")),
    ),
    SetupStep(
        number=8,
        name="Browser Setup",
        description="Playwright + headless Chromium",
        script="scripts/08-browser-setup.sh",
        check_done=lambda: _cmd_exists("playwright"),
    ),
    SetupStep(
        number=9,
        name="n8n Automation",
        description="n8n + PostgreSQL Docker stack",
        script="scripts/09-n8n-setup.sh",
        check_done=lambda: _n8n_running(),
    ),
]


def _n8n_running() -> bool:
    out = run_cmd(
        "docker ps --filter name=n8n --filter status=running --format '{{.Names}}' 2>/dev/null",
        timeout=5,
    )
    return bool(out and "n8n" in out and not out.startswith("Error"))


def check_setup_status() -> list[tuple[SetupStep, bool]]:
    """Return all setup steps with their done status."""
    return [(step, step.check_done()) for step in SETUP_STEPS]


def run_setup_step(step: SetupStep) -> tuple[bool, str]:
    """Run a setup script. Returns (success, output)."""
    script_path = Path(__file__).parent.parent.parent / step.script
    if not script_path.exists():
        return False, f"Script not found: {step.script}"

    output = run_cmd(f"sudo bash {script_path}", timeout=300)
    done = step.check_done()
    return done, output
