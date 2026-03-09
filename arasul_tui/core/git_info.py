from __future__ import annotations

import shlex
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from arasul_tui.core.shell import run_cmd


def parse_gh_account(auth_output: str) -> str:
    """Extract GitHub account name from 'gh auth status' output.

    Handles multiple output formats:
      - "account <name>"           (older gh)
      - "Logged in to ... as <name> (keyring)"  (newer gh)
    """
    for line in auth_output.splitlines():
        lower = line.lower()
        # Newer gh format: "Logged in to github.com as username (keyring)"
        if " as " in lower and ("logged in" in lower or "github.com" in lower):
            parts = line.strip().split()
            for i, p in enumerate(parts):
                if p.lower() == "as" and i + 1 < len(parts):
                    return parts[i + 1].strip("()")
        # Older gh format: "account username"
        if "account" in lower:
            parts = line.strip().split()
            for i, p in enumerate(parts):
                if p.lower() == "account" and i + 1 < len(parts):
                    return parts[i + 1]
    return ""


@dataclass
class GitInfo:
    branch: str = ""
    is_dirty: bool = False
    short_hash: str = ""
    commit_message: str = ""
    commit_time: str = ""
    remote_url: str = ""
    has_remote: bool = False


def get_git_info(project: Path) -> GitInfo | None:
    """Extract git metadata from a project directory."""
    if not (project / ".git").exists():
        return None

    def _clean(val: str) -> str:
        """Strip run_cmd error strings so they don't leak into UI."""
        return "" if val.startswith("Error") else val

    q = shlex.quote(str(project))
    branch = _clean(run_cmd(f"git -C {q} symbolic-ref --short HEAD 2>/dev/null"))
    # Detached HEAD: symbolic-ref fails, fall back to short commit hash
    if not branch:
        branch = _clean(run_cmd(f"git -C {q} rev-parse --short HEAD 2>/dev/null"))
        if branch:
            branch = f"({branch})"  # indicate detached HEAD

    dirty_out = run_cmd(f"git -C {q} status --porcelain 2>/dev/null")
    is_dirty = bool(dirty_out and not dirty_out.startswith("Error"))
    short_hash = _clean(run_cmd(f"git -C {q} log -1 --format=%h 2>/dev/null"))
    commit_msg = _clean(run_cmd(f"git -C {q} log -1 --format=%s 2>/dev/null"))
    commit_time = _clean(run_cmd(f"git -C {q} log -1 --format=%cr 2>/dev/null"))
    remote_url = _clean(run_cmd(f"git -C {q} remote get-url origin 2>/dev/null"))

    return GitInfo(
        branch=branch,
        is_dirty=is_dirty,
        short_hash=short_hash,
        commit_message=commit_msg[:60],
        commit_time=commit_time,
        remote_url=remote_url,
        has_remote=bool(remote_url),
    )


def detect_language(project: Path) -> str:
    """Detect dominant languages in a project by file extension."""
    ext_map = {
        ".py": "Python",
        ".js": "JavaScript",
        ".ts": "TypeScript",
        ".tsx": "TypeScript",
        ".jsx": "JavaScript",
        ".rs": "Rust",
        ".go": "Go",
        ".java": "Java",
        ".rb": "Ruby",
        ".sh": "Shell",
        ".bash": "Shell",
        ".c": "C",
        ".cpp": "C++",
        ".h": "C/C++",
        ".lua": "Lua",
        ".zig": "Zig",
        ".swift": "Swift",
        ".kt": "Kotlin",
        ".scala": "Scala",
        ".cs": "C#",
    }

    _skip_dirs = {
        "node_modules",
        "venv",
        ".venv",
        "__pycache__",
        "dist",
        "build",
        ".git",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        "env",
        ".eggs",
    }

    counter: Counter[str] = Counter()
    try:
        for f in project.rglob("*"):
            parts = f.relative_to(project).parts
            if any(p in _skip_dirs or p.startswith(".") for p in parts):
                continue
            if f.is_file():
                lang = ext_map.get(f.suffix.lower())
                if lang:
                    counter[lang] += 1
    except Exception:
        pass

    if not counter:
        return ""

    top = counter.most_common(3)
    return " / ".join(lang for lang, _ in top)


def get_readme_headline(project: Path) -> str:
    """Return the first meaningful line from README.md."""
    for name in ("README.md", "readme.md", "README.rst", "README.txt", "README"):
        readme = project / name
        if readme.exists():
            try:
                for line in readme.read_text(encoding="utf-8", errors="replace").splitlines():
                    stripped = line.strip().lstrip("#").strip()
                    if stripped and not stripped.startswith("["):
                        return stripped[:80]
            except Exception:
                pass
    return ""


def get_disk_usage(project: Path) -> str:
    """Return human-readable disk usage of a directory."""
    result = run_cmd(f"du -sh {shlex.quote(str(project))} 2>/dev/null", timeout=5)
    if result and not result.startswith("Error"):
        return result.split()[0]
    return ""
