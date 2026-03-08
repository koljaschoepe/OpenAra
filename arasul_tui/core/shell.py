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
        return (proc.stdout or proc.stderr or "").strip()
    except subprocess.TimeoutExpired:
        return "Error: command timed out"
    except OSError as exc:
        return f"Error: {exc}"
