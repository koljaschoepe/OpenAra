"""Search and listing tools for the Open Ara agent.

search_files: grep-like pattern search across source files.
list_files: directory listing with sizes.

Uses system grep when available (much faster on large repos).
Falls back to Python re for portability.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from arasul_tui.agent.tools._base import ToolError, safe_path

_MAX_RESULTS = 50
_MAX_LIST_DEPTH = 3
_MAX_LIST_ENTRIES = 200

# Extensions treated as source files (not binary)
_SOURCE_EXTS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java",
    ".c", ".cpp", ".h", ".hpp", ".cs", ".rb", ".php", ".swift",
    ".kt", ".scala", ".r", ".sh", ".bash", ".zsh", ".fish",
    ".yaml", ".yml", ".toml", ".json", ".xml", ".html", ".css",
    ".scss", ".sass", ".md", ".rst", ".txt", ".env.example",
    ".sql", ".graphql", ".proto",
}

# Directories always skipped
_SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", "env",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build",
    ".next", ".nuxt", "target", "*.egg-info",
}


def _is_skippable(path: Path) -> bool:
    return path.name in _SKIP_DIRS or path.name.endswith(".egg-info")


async def search_files(
    pattern: str,
    project_path: Path,
    file_pattern: str = "*",
    case_sensitive: bool = False,
) -> str:
    if not pattern:
        raise ToolError("Search pattern cannot be empty.")

    # Validate regex in Python first — grep would silently accept some patterns
    # that differ from Python re, and we want consistent error messages.
    try:
        re.compile(pattern, 0 if case_sensitive else re.IGNORECASE)
    except re.error as exc:
        raise ToolError(f"Invalid regex pattern: {exc}") from exc

    if shutil.which("grep"):
        return _grep_search(pattern, project_path, file_pattern, case_sensitive)
    return _python_search(pattern, project_path, file_pattern, case_sensitive)


def _grep_search(
    pattern: str,
    project_path: Path,
    file_pattern: str,
    case_sensitive: bool,
) -> str:
    args = ["grep", "-rn", "--include", file_pattern]
    if not case_sensitive:
        args.append("-i")
    # Exclude noise dirs
    for skip in _SKIP_DIRS:
        args += ["--exclude-dir", skip]
    args += [pattern, str(project_path)]

    try:
        result = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        raise ToolError("Search timed out. Try a more specific pattern.")
    except OSError as exc:
        raise ToolError(f"grep failed: {exc}") from exc

    raw = result.stdout.decode(errors="replace")
    if not raw.strip():
        return f"No matches found for {pattern!r}"

    lines = raw.splitlines()
    # Make paths relative
    prefix = str(project_path) + "/"
    lines = [l.replace(prefix, "") for l in lines]

    if len(lines) > _MAX_RESULTS:
        lines = lines[:_MAX_RESULTS]
        lines.append(f"... ({len(lines)} results shown, use a more specific pattern)")

    return f"Found matches for {pattern!r}:\n" + "\n".join(lines)


def _python_search(
    pattern: str,
    project_path: Path,
    file_pattern: str,
    case_sensitive: bool,
) -> str:
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        rx = re.compile(pattern, flags)
    except re.error as exc:
        raise ToolError(f"Invalid regex pattern: {exc}") from exc

    matches: list[str] = []

    for f in project_path.rglob(file_pattern):
        if not f.is_file():
            continue
        if any(_is_skippable(p) for p in f.parents):
            continue
        if f.suffix not in _SOURCE_EXTS:
            continue
        try:
            for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if rx.search(line):
                    rel = f.relative_to(project_path)
                    matches.append(f"{rel}:{i}: {line.strip()}")
                    if len(matches) >= _MAX_RESULTS:
                        break
        except OSError:
            continue
        if len(matches) >= _MAX_RESULTS:
            break

    if not matches:
        return f"No matches found for {pattern!r}"

    return f"Found {len(matches)} match(es) for {pattern!r}:\n" + "\n".join(matches)


async def list_files(
    project_path: Path,
    path: str = ".",
    recursive: bool = False,
) -> str:
    target = safe_path(project_path, path)

    if not target.exists():
        raise ToolError(f"Path not found: {path}")
    if not target.is_dir():
        # Single file info
        stat = target.stat()
        return f"{path}: {_fmt_size(stat.st_size)}, modified {_fmt_time(stat.st_mtime)}"

    entries: list[str] = []
    _collect_entries(target, project_path, entries, depth=0, recursive=recursive)

    if not entries:
        return f"Directory is empty: {path}"
    if len(entries) > _MAX_LIST_ENTRIES:
        entries = entries[:_MAX_LIST_ENTRIES]
        entries.append(f"... (showing {_MAX_LIST_ENTRIES} entries, directory has more)")

    header = f"Directory: {path}/ ({len(entries)} entries)"
    return header + "\n" + "\n".join(entries)


def _collect_entries(
    directory: Path,
    project_root: Path,
    out: list[str],
    depth: int,
    recursive: bool,
) -> None:
    if depth > _MAX_LIST_DEPTH:
        return
    if len(out) >= _MAX_LIST_ENTRIES:
        return

    indent = "  " * depth
    try:
        items = sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except PermissionError:
        return

    for item in items:
        if _is_skippable(item):
            continue
        if len(out) >= _MAX_LIST_ENTRIES:
            return

        rel = item.relative_to(project_root)
        if item.is_dir():
            out.append(f"{indent}{item.name}/")
            if recursive:
                _collect_entries(item, project_root, out, depth + 1, recursive)
        else:
            try:
                size = _fmt_size(item.stat().st_size)
            except OSError:
                size = "?"
            out.append(f"{indent}{item.name}  ({size})")


def _fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / 1024 / 1024:.1f} MB"


def _fmt_time(ts: float) -> str:
    from datetime import datetime
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
