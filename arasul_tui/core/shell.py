from __future__ import annotations

import subprocess


def run_cmd(cmd: str, timeout: int = 4) -> str:
    """Run a shell command and return stripped output.

    Uses shell=True because callers rely on shell features (pipes,
    redirects, ``2>&1``).  Only pass **trusted, internally-built**
    command strings — never include unsanitised user input.
    """
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            check=False,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        if proc.returncode != 0 and not stdout:
            return f"Error: {stderr}" if stderr else "Error: command failed"
        return stdout or stderr or ""
    except subprocess.TimeoutExpired:
        return "Error: command timed out"
    except OSError as exc:
        return f"Error: {exc}"
