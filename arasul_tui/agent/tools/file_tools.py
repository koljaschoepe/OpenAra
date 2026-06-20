"""File read/write tools for the Open Ara agent.

All paths are validated against project_root to prevent traversal.
write_file uses atomic replace (temp file + rename) to avoid corruption.
"""

from __future__ import annotations

import difflib
import os
import shutil
import tempfile
import time
from pathlib import Path

from arasul_tui.agent.tools._base import ToolError, safe_path

_MAX_READ_LINES = 500
_MAX_FILE_BYTES = 200_000  # 200 KB sanity cap for writes
_BACKUP_DIR = ".openara-backups"
_MAX_BACKUPS_PER_FILE = 10


async def read_file(
    path: str,
    project_path: Path,
    start_line: int | None = None,
    end_line: int | None = None,
) -> str:
    target = safe_path(project_path, path)

    if not target.exists():
        raise ToolError(f"File not found: {path}")
    if not target.is_file():
        raise ToolError(f"Not a file: {path}")

    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ToolError(f"Cannot read {path}: {exc}") from exc

    lines = text.splitlines(keepends=True)
    total = len(lines)

    # Line range (1-based, inclusive)
    lo = max(1, start_line or 1)
    hi = min(total, end_line or total)

    # Clamp to _MAX_READ_LINES when no explicit range given
    if start_line is None and end_line is None and total > _MAX_READ_LINES:
        hi = _MAX_READ_LINES

    selected = lines[lo - 1 : hi]
    truncated = hi < total and end_line is None

    header = f"File: {path} ({total} lines)"
    if start_line or end_line:
        header += f" — showing lines {lo}–{hi}"
    elif truncated:
        header += f" — showing first {_MAX_READ_LINES} lines (use start_line/end_line for more)"

    numbered = "".join(f"{lo + i}: {line}" for i, line in enumerate(selected))
    return f"{header}\n\n{numbered}"


def _backup_file(target: Path, project_root: Path) -> Path | None:
    """Save existing file to .openara-backups/ before overwriting. Returns backup path."""
    if not target.exists() or not target.is_file():
        return None
    try:
        rel = target.relative_to(project_root)
    except ValueError:
        return None

    backup_dir = project_root / _BACKUP_DIR / rel
    backup_dir.mkdir(parents=True, exist_ok=True)

    # nanoseconds for uniqueness even in rapid successive calls
    backup_path = backup_dir / f"{time.time_ns()}.bak"
    shutil.copy2(target, backup_path)

    # Prune oldest backups beyond the limit
    old_backups = sorted(backup_dir.glob("*.bak"))[:-_MAX_BACKUPS_PER_FILE]
    for old in old_backups:
        old.unlink(missing_ok=True)

    return backup_path


async def write_file(
    path: str,
    content: str,
    project_path: Path,
) -> str:
    if len(content.encode()) > _MAX_FILE_BYTES:
        raise ToolError(
            f"Content too large ({len(content.encode()) // 1024} KB). Max is 200 KB."
        )

    target = safe_path(project_path, path)
    target.parent.mkdir(parents=True, exist_ok=True)

    # Backup existing file before overwriting so undo_file can restore it
    is_update = target.exists() and target.is_file()
    if is_update:
        _backup_file(target, project_path)

    # Compute diff for the return message
    old_lines: list[str] = []
    if is_update:
        try:
            old_lines = target.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        except OSError:
            pass

    new_lines = content.splitlines(keepends=True)

    # Atomic write: temp file in same dir, then rename
    try:
        fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=".ara.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp, str(target))
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except OSError as exc:
        raise ToolError(f"Cannot write {path}: {exc}") from exc

    # Summary
    if old_lines:
        diff = list(
            difflib.unified_diff(
                old_lines, new_lines,
                fromfile=f"a/{path}", tofile=f"b/{path}",
                lineterm="",
            )
        )
        added = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
        removed = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))
        return f"File updated: {path} (+{added}/-{removed} lines, {len(new_lines)} total)"
    else:
        return f"File created: {path} ({len(new_lines)} lines)"


async def undo_file(path: str, project_path: Path) -> str:
    """Restore a file to its state before the last write_file call."""
    target = safe_path(project_path, path)
    try:
        rel = target.relative_to(project_path)
    except ValueError:
        raise ToolError(f"Path outside project: {path}")

    backup_dir = project_path / _BACKUP_DIR / rel
    if not backup_dir.exists():
        return f"No backup found for: {path} (was it never overwritten this session?)"

    backups = sorted(backup_dir.glob("*.bak"), reverse=True)
    if not backups:
        return f"No backup found for: {path}"

    latest = backups[0]
    shutil.copy2(latest, target)
    latest.unlink(missing_ok=True)
    remaining = len(backups) - 1
    more = f" ({remaining} older version{'s' if remaining != 1 else ''} available)" if remaining else ""
    return f"Restored: {path} to previous version{more}"


def diff_for_approval(path: str, new_content: str, project_path: Path) -> str:
    """Return a unified diff string for the approval UI without writing anything."""
    target = safe_path(project_path, path)
    old_lines: list[str] = []
    if target.exists() and target.is_file():
        try:
            old_lines = target.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        except OSError:
            pass

    new_lines = new_content.splitlines(keepends=True)
    diff = difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f"a/{path}", tofile=f"b/{path}",
        lineterm="",
    )
    result = "\n".join(diff)
    if not result and not old_lines:
        preview = new_content[:400]
        return f"(new file)\n{preview}" + (" ..." if len(new_content) > 400 else "")
    return result or "(no changes)"
