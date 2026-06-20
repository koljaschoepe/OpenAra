from __future__ import annotations

from pathlib import Path


class ToolError(Exception):
    """Raised when a tool fails in an expected, user-readable way."""


def safe_path(project_root: Path, user_path: str) -> Path:
    """Resolve *user_path* relative to *project_root* and reject traversal.

    Raises ToolError if the resolved path escapes the project directory.
    """
    if not user_path or user_path.strip() == "":
        raise ToolError("Path cannot be empty.")

    root = project_root.resolve()
    target = (root / user_path).resolve()

    try:
        target.relative_to(root)
    except ValueError:
        raise ToolError(
            f"Path '{user_path}' is outside the project directory. "
            "Only paths within the project are allowed."
        )
    return target
