"""Shared helpers for reading/writing ~/.claude.json."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile

from arasul_tui.core.constants import CLAUDE_JSON


def load_claude_json() -> dict:
    """Load ~/.claude.json, returning empty dict on failure."""
    try:
        return json.loads(CLAUDE_JSON.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_claude_json(data: dict) -> None:
    """Write ~/.claude.json atomically to prevent corruption."""
    content = json.dumps(data, indent=2) + "\n"
    CLAUDE_JSON.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(CLAUDE_JSON.parent),
        prefix=".claude.json.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, str(CLAUDE_JSON))
        # Ensure final file also has restricted permissions
        os.chmod(str(CLAUDE_JSON), 0o600)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise
