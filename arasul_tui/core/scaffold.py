"""Default project scaffolding — .claude/ directory, CLAUDE.md, docs/.

Creates a consistent baseline for every new project so that Claude Code
has context from the very first session.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path


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

    lines += [
        "",
        "## Architecture & Patterns",
        "<!-- Update this section as the project evolves.",
        "     Document key architectural decisions, data models,",
        "     and design patterns used. -->",
        "",
        "## Build & Test",
        "<!-- Document build commands, test commands, and",
        "     development workflow as they are established. -->",
        "",
        "## Important Files",
        "<!-- List key files and their purposes as the",
        "     codebase grows. -->",
        "",
        "## Self-Maintenance",
        "",
        "When working on this project, update this CLAUDE.md with:",
        "- Architectural decisions and their rationale",
        "- Build/test commands as they are established",
        "- Key file paths and their purposes",
        "- Coding conventions specific to this project",
        "",
        "Keep this file under 200 lines for optimal context usage.",
        "",
    ]

    return "\n".join(lines)


def scaffold_defaults(
    project_dir: Path,
    name: str,
    *,
    skip_claude_md: bool = False,
) -> None:
    """Create default project structure.

    Creates:
      - .claude/settings.json    (base permission guardrails)
      - .claude/commands/.gitkeep (custom slash commands)
      - .claude/agents/.gitkeep   (subagent definitions)
      - CLAUDE.md                 (self-learning starter, unless skip_claude_md)
      - docs/.gitkeep             (documentation directory)

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

    # docs/
    docs_dir = project_dir / "docs"
    docs_dir.mkdir(exist_ok=True)
    gitkeep = docs_dir / ".gitkeep"
    if not gitkeep.exists():
        gitkeep.write_text("")


def scaffold_clone_defaults(project_dir: Path, name: str) -> None:
    """Add missing default files to a cloned project (merge strategy).

    Only creates files that don't already exist — never overwrites
    anything the repo author has set up.
    """
    scaffold_defaults(project_dir, name)
