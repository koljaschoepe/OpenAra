"""Shell command execution tool for the Open Ara agent.

Runs in the project directory with a hard timeout.
Interactive stdin is devnull to prevent hanging.
Blocks obvious filesystem-destroying patterns unconditionally.
"""

from __future__ import annotations

import re
import shlex
import subprocess
from pathlib import Path

from arasul_tui.agent.tools._base import ToolError

_DEFAULT_TIMEOUT = 30
_MAX_TIMEOUT = 120
_MAX_OUTPUT_BYTES = 32_000  # ~8k tokens — trim before sending to LLM

_BLOCKED: list[re.Pattern] = [
    re.compile(r">\s*/dev/(sd|nvme|mmcblk|hd)"),  # writes to block devices
    re.compile(r"\bdd\b.+\bof=/dev/"),             # dd to device
    re.compile(r":\(\)\s*\{"),                     # fork bomb
    re.compile(r"\bmkfs\b"),                       # filesystem format
]


def _is_rm_rf(command: str) -> bool:
    """Detect `rm -rf`, `rm -fr`, `rm -Rf` and similar variants via flag parsing."""
    try:
        parts = shlex.split(command)
    except ValueError:
        return False
    if not parts or parts[0] not in ("rm", "/bin/rm", "/usr/bin/rm"):
        return False
    for part in parts[1:]:
        if part.startswith("-") and not part.startswith("--"):
            flags = part[1:]
            if "f" in flags and ("r" in flags or "R" in flags):
                return True
    return False


def _is_blocked(command: str) -> str | None:
    if _is_rm_rf(command):
        return "Command blocked — 'rm -rf' variants are never permitted."
    for pattern in _BLOCKED:
        if pattern.search(command):
            return f"Command blocked — matches dangerous pattern: {pattern.pattern!r}"
    return None


async def run_command(
    command: str,
    project_path: Path,
    timeout: int = _DEFAULT_TIMEOUT,
) -> str:
    block_reason = _is_blocked(command)
    if block_reason:
        raise ToolError(block_reason)

    effective_timeout = min(max(1, timeout), _MAX_TIMEOUT)

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=str(project_path),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=effective_timeout,
        )
    except subprocess.TimeoutExpired:
        raise ToolError(
            f"Command timed out after {effective_timeout}s: {command!r}\n"
            "Use a larger timeout or run a faster command."
        )
    except OSError as exc:
        raise ToolError(f"Failed to run command: {exc}") from exc

    stdout = result.stdout.decode(errors="replace")
    stderr = result.stderr.decode(errors="replace")

    # Trim oversized output before it inflates context
    combined = stdout + ("\n--- stderr ---\n" + stderr if stderr.strip() else "")
    if len(combined.encode()) > _MAX_OUTPUT_BYTES:
        combined = combined[:_MAX_OUTPUT_BYTES] + f"\n... (truncated, total {len(combined)} chars)"

    lines = [f"Exit code: {result.returncode}"]
    if stdout.strip():
        lines.append(f"stdout:\n{stdout.rstrip()}")
    if stderr.strip():
        lines.append(f"stderr:\n{stderr.rstrip()}")
    if not stdout.strip() and not stderr.strip():
        lines.append("(no output)")

    return "\n".join(lines)
