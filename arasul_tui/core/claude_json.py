"""Shared helpers for reading/writing ~/.claude.json."""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import tempfile
from collections.abc import Callable

from arasul_tui.core.constants import CLAUDE_JSON

# Lock file for coordinating read-modify-write cycles
_LOCK_PATH = CLAUDE_JSON.parent / ".claude.json.lock"


def _acquire_lock() -> int:
    """Acquire exclusive lock for claude.json operations."""
    CLAUDE_JSON.parent.mkdir(parents=True, exist_ok=True)
    lock_fd = os.open(str(_LOCK_PATH), os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(lock_fd, fcntl.LOCK_EX)
    return lock_fd


def _release_lock(lock_fd: int) -> None:
    """Release the file lock."""
    fcntl.flock(lock_fd, fcntl.LOCK_UN)
    os.close(lock_fd)


def load_claude_json() -> dict:
    """Load ~/.claude.json, returning empty dict on failure."""
    try:
        return json.loads(CLAUDE_JSON.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def save_claude_json(data: dict) -> None:
    """Write ~/.claude.json atomically with file locking."""
    content = json.dumps(data, indent=2) + "\n"
    CLAUDE_JSON.parent.mkdir(parents=True, exist_ok=True)

    lock_fd = _acquire_lock()
    try:
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
            os.chmod(str(CLAUDE_JSON), 0o600)
        except Exception:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise
    finally:
        _release_lock(lock_fd)


def update_claude_json(updater: Callable[[dict], None]) -> None:
    """Locked read-modify-write for ~/.claude.json.

    ``updater`` is a callable ``(dict) -> None`` that mutates the dict in place.
    The lock is held for the entire read-modify-write cycle, preventing TOCTOU
    races when multiple processes modify the file concurrently.
    """
    lock_fd = _acquire_lock()
    try:
        # Read under lock
        try:
            data = json.loads(CLAUDE_JSON.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            data = {}

        # Mutate
        updater(data)

        # Write
        content = json.dumps(data, indent=2) + "\n"
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
            os.chmod(str(CLAUDE_JSON), 0o600)
        except Exception:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise
    finally:
        _release_lock(lock_fd)
