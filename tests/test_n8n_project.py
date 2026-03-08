from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from arasul_tui.core.n8n_project import (
    is_n8n_project_name,
    scaffold_n8n_project,
)


def test_is_n8n_project_name_exact():
    assert is_n8n_project_name("n8n-workflows") is True


def test_is_n8n_project_name_with_spaces():
    assert is_n8n_project_name("n8n workflows") is True


def test_is_n8n_project_name_uppercase():
    assert is_n8n_project_name("N8N-Workflows") is True


def test_is_n8n_project_name_false():
    assert is_n8n_project_name("my-project") is False
    assert is_n8n_project_name("n8n") is False


def test_scaffold_creates_directories(tmp_path: Path):
    project = tmp_path / "n8n-workflows"
    project.mkdir()
    scaffold_n8n_project(project)

    assert (project / "workflows").is_dir()
    assert (project / "docs").is_dir()
    assert (project / ".claude").is_dir()


def test_scaffold_creates_claude_md(tmp_path: Path):
    project = tmp_path / "n8n-workflows"
    project.mkdir()
    scaffold_n8n_project(project, n8n_url="http://myjetson:5678")

    claude_md = project / "CLAUDE.md"
    assert claude_md.exists()
    content = claude_md.read_text()
    assert "http://myjetson:5678" in content
    assert "n8n Workflow Automation" in content


def test_scaffold_creates_settings_json(tmp_path: Path):
    project = tmp_path / "n8n-workflows"
    project.mkdir()
    scaffold_n8n_project(project)

    settings_file = project / ".claude" / "settings.json"
    assert settings_file.exists()
    settings = json.loads(settings_file.read_text())
    assert "permissions" in settings
    assert "deny" in settings["permissions"]
    deny = settings["permissions"]["deny"]
    assert any("docker" in d for d in deny)
    assert any("sudo" in d for d in deny)


def test_scaffold_default_url(tmp_path: Path):
    project = tmp_path / "n8n-workflows"
    project.mkdir()
    scaffold_n8n_project(project)

    content = (project / "CLAUDE.md").read_text()
    assert "http://localhost:5678" in content


def test_scaffold_fallback_no_template(tmp_path: Path):
    project = tmp_path / "n8n-workflows"
    project.mkdir()

    with (
        patch("arasul_tui.core.n8n_project._TEMPLATE", Path("/nonexistent/template")),
        patch("arasul_tui.core.n8n_project._SETTINGS", Path("/nonexistent/settings")),
    ):
        result = scaffold_n8n_project(project)

    assert result is True
    assert (project / "CLAUDE.md").exists()
    assert (project / ".claude" / "settings.json").exists()
    # Fallback content
    content = (project / "CLAUDE.md").read_text()
    assert "n8n" in content


def test_scaffold_idempotent(tmp_path: Path):
    project = tmp_path / "n8n-workflows"
    project.mkdir()
    scaffold_n8n_project(project)
    scaffold_n8n_project(project)  # second call should not fail

    assert (project / "CLAUDE.md").exists()
    assert (project / "workflows").is_dir()


def test_create_n8n_project_integration(state_with_projects):
    """Creating a project named n8n-workflows triggers scaffolding."""
    from arasul_tui.commands.project import _create_finish

    result = _create_finish(state_with_projects, "n8n-workflows")
    assert result.ok is True

    target = state_with_projects.project_root / "n8n-workflows"
    assert target.exists()
    assert (target / "CLAUDE.md").exists()
    assert (target / "workflows").is_dir()
    assert (target / ".claude" / "settings.json").exists()
