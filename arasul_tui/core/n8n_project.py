"""Scaffold an n8n-workflows project with CLAUDE.md template and guardrails."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

N8N_URL_DEFAULT = "http://localhost:5678"

# Paths relative to the repo checkout
_REPO_CONFIG = Path(__file__).parent.parent.parent / "config" / "n8n"
_TEMPLATE = _REPO_CONFIG / "CLAUDE.md.template"
_SETTINGS = _REPO_CONFIG / "settings.json"

# Name that triggers n8n scaffolding
N8N_PROJECT_NAME = "n8n-workflows"


def is_n8n_project_name(name: str) -> bool:
    """Check if the project name should trigger n8n scaffolding."""
    return name.lower().replace(" ", "-") == N8N_PROJECT_NAME


def scaffold_n8n_project(project_dir: Path, n8n_url: str | None = None) -> bool:
    """Set up n8n project structure in an existing directory.

    Creates:
      - workflows/          (workflow JSON backups)
      - docs/               (project documentation)
      - CLAUDE.md           (from template, with URL substituted)
      - .claude/settings.json (guardrails)

    Returns True on success.
    """
    url = n8n_url or N8N_URL_DEFAULT

    # Subdirectories
    (project_dir / "workflows").mkdir(exist_ok=True)
    (project_dir / "docs").mkdir(exist_ok=True)

    # CLAUDE.md from template
    if _TEMPLATE.exists():
        content = _TEMPLATE.read_text()
        content = content.replace("{{N8N_URL}}", url)
        (project_dir / "CLAUDE.md").write_text(content)
    else:
        # Minimal fallback if template is missing
        (project_dir / "CLAUDE.md").write_text(
            f"# n8n Workflow Automation\n\nn8n Web-UI: {url}\nn8n API: {url}/api/v1\nWorkflow backups: ./workflows/\n"
        )

    # .claude/settings.json (guardrails)
    claude_dir = project_dir / ".claude"
    claude_dir.mkdir(exist_ok=True)
    if _SETTINGS.exists():
        shutil.copy2(_SETTINGS, claude_dir / "settings.json")
    else:
        # Minimal fallback
        from arasul_tui.core.n8n_client import n8n_dir

        nd = n8n_dir()
        settings = {
            "permissions": {
                "deny": [
                    "Bash(docker *)",
                    "Bash(sudo *)",
                    f"Edit({nd}/*)",
                    "Edit(/etc/*)",
                    f"Read({nd}/.env)",
                ]
            }
        }
        (claude_dir / "settings.json").write_text(json.dumps(settings, indent=2) + "\n")

    return True
