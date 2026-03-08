"""User configuration (persisted in ~/.config/arasul/config.json)."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "arasul"
CONFIG_FILE = CONFIG_DIR / "config.json"


def _load() -> dict:
    try:
        return json.loads(CONFIG_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(CONFIG_DIR), prefix=".config.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, str(CONFIG_FILE))
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


def get_display_name() -> str:
    """Return the user's display name, or empty string if not set."""
    return _load().get("display_name", "")


def set_display_name(name: str) -> None:
    """Save the user's display name."""
    data = _load()
    data["display_name"] = name
    _save(data)
