"""Default project scaffolding — .claude/ directory, CLAUDE.md, docs/.

Creates a consistent baseline for every new project so that Claude Code
has context from the very first session.  Includes self-learning docs
that Claude maintains automatically in the background.
"""

from __future__ import annotations

import datetime
import json
import shutil
from pathlib import Path

# Template directories shipped with the repo
_REPO_ROOT = Path(__file__).parent.parent.parent
DOCS_TEMPLATE_DIR = _REPO_ROOT / "config" / "project-docs"


def _base_settings() -> dict:
    """Base .claude/settings.json with safe deny rules."""
    return {
        "permissions": {
            "deny": [
                "Bash(rm -rf /)",
                "Bash(sudo rm -rf *)",
            ]
        }
    }


def _copy_template_files(src_dir: Path, dst_dir: Path) -> None:
    """Copy files from src to dst, skipping files that already exist."""
    dst_dir.mkdir(parents=True, exist_ok=True)
    if not src_dir.exists():
        return
    for f in sorted(src_dir.iterdir()):
        if f.is_file():
            target = dst_dir / f.name
            if not target.exists():
                shutil.copy2(f, target)


def _self_learning_section() -> str:
    """Universal self-learning block appended to every CLAUDE.md."""
    return """
## Self-Learning

This project uses automatic context tracking. As you work, silently
maintain these files in the background without asking:

- `docs/tasks.md` — Move completed items to Done, add new items to Todo
- `docs/lessons.md` — Log patterns learned and mistakes to avoid
- `docs/decisions.md` — Record architectural choices with rationale
- `docs/changelog.md` — Append a dated summary after significant work

When you get corrected or make a mistake, add a rule under "## Rules"
below to prevent repeating it.

As you discover project conventions (test commands, linting, build steps,
coding patterns), add them to the relevant sections in this file.

Keep this file under 200 lines. Be concise.

## Build & Test
<!-- Auto-populated: add commands as they are discovered -->

## Architecture & Patterns
<!-- Auto-populated: document structure as the project evolves -->

## Key Files
<!-- Auto-populated: list important files and their purposes -->

## Rules
<!-- Auto-populated: add rules when mistakes happen to prevent repeats -->
"""


def _starter_claude_md(project_name: str) -> str:
    """Generate a self-learning CLAUDE.md with platform context."""
    from arasul_tui.core.platform import get_platform

    p = get_platform()
    today = datetime.date.today().isoformat()

    lines = [
        f"# {project_name}",
        "",
        "## Quick Info",
        f"- Created: {today}",
        f"- Platform: {p.display_name} ({p.arch})",
        f"- Storage: {p.storage.mount}",
    ]

    if p.gpu.has_cuda:
        lines.append(f"- GPU: CUDA {p.gpu.cuda_version or '12.6'}")

    result = "\n".join(lines) + "\n"
    result += _self_learning_section()
    return result


def scaffold_defaults(
    project_dir: Path,
    name: str,
    *,
    skip_claude_md: bool = False,
) -> None:
    """Create default project structure.

    Creates:
      - .claude/settings.json     (base permission guardrails)
      - .claude/commands/.gitkeep  (custom slash commands)
      - .claude/agents/.gitkeep    (subagent definitions)
      - CLAUDE.md                  (self-learning starter, unless skip_claude_md)
      - docs/                      (tasks, lessons, decisions, changelog)

    Safe to call multiple times (idempotent).
    """
    # .claude/ directory + settings
    claude_dir = project_dir / ".claude"
    claude_dir.mkdir(exist_ok=True)

    settings_path = claude_dir / "settings.json"
    if not settings_path.exists():
        settings_path.write_text(json.dumps(_base_settings(), indent=2) + "\n")

    # .claude/commands/
    commands_dir = claude_dir / "commands"
    commands_dir.mkdir(exist_ok=True)
    gitkeep = commands_dir / ".gitkeep"
    if not gitkeep.exists():
        gitkeep.write_text("")

    # .claude/agents/
    agents_dir = claude_dir / "agents"
    agents_dir.mkdir(exist_ok=True)
    gitkeep = agents_dir / ".gitkeep"
    if not gitkeep.exists():
        gitkeep.write_text("")

    # CLAUDE.md
    if not skip_claude_md:
        claude_md = project_dir / "CLAUDE.md"
        if not claude_md.exists():
            claude_md.write_text(_starter_claude_md(name))

    # docs/ — copy starter docs from templates
    docs_dir = project_dir / "docs"
    _copy_template_files(DOCS_TEMPLATE_DIR, docs_dir)


def scaffold_clone_defaults(project_dir: Path, name: str) -> None:
    """Add missing default files to a cloned project (merge strategy).

    Only creates files that don't already exist — never overwrites
    anything the repo author has set up.
    """
    scaffold_defaults(project_dir, name)
