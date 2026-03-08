"""Tests for default project scaffolding."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from arasul_tui.core.scaffold import (
    _base_settings,
    _starter_claude_md,
    scaffold_clone_defaults,
    scaffold_defaults,
)


def _mock_platform():
    """Create a mock Platform for testing."""
    from unittest.mock import MagicMock

    p = MagicMock()
    p.display_name = "Jetson Orin Nano"
    p.arch = "aarch64"
    p.storage.mount = Path("/mnt/nvme")
    p.gpu.has_cuda = True
    p.gpu.cuda_version = "12.6"
    return p


def test_base_settings_has_deny_rules():
    s = _base_settings()
    assert "permissions" in s
    assert "deny" in s["permissions"]
    assert len(s["permissions"]["deny"]) >= 2


def test_starter_claude_md_contains_project_name():
    with patch("arasul_tui.core.platform.get_platform", return_value=_mock_platform()):
        md = _starter_claude_md("my-app")
    assert "# my-app" in md
    assert "Jetson Orin Nano" in md
    assert "aarch64" in md
    assert "Self-Learning" in md


def test_starter_claude_md_includes_cuda():
    with patch("arasul_tui.core.platform.get_platform", return_value=_mock_platform()):
        md = _starter_claude_md("gpu-project")
    assert "CUDA" in md


def test_starter_claude_md_no_cuda_on_rpi():
    p = _mock_platform()
    p.gpu.has_cuda = False
    with patch("arasul_tui.core.platform.get_platform", return_value=p):
        md = _starter_claude_md("rpi-project")
    assert "CUDA" not in md


def test_scaffold_defaults_creates_all_dirs(tmp_path: Path):
    project = tmp_path / "my-app"
    project.mkdir()
    with patch("arasul_tui.core.platform.get_platform", return_value=_mock_platform()):
        scaffold_defaults(project, "my-app")

    assert (project / ".claude").is_dir()
    assert (project / ".claude" / "settings.json").is_file()
    assert (project / ".claude" / "commands").is_dir()
    assert (project / ".claude" / "commands" / ".gitkeep").exists()
    assert (project / ".claude" / "agents").is_dir()
    assert (project / ".claude" / "agents" / ".gitkeep").exists()
    assert (project / "CLAUDE.md").is_file()
    assert (project / "docs").is_dir()
    assert (project / "docs" / "tasks.md").exists()
    assert (project / "docs" / "lessons.md").exists()
    assert (project / "docs" / "decisions.md").exists()
    assert (project / "docs" / "changelog.md").exists()


def test_scaffold_defaults_settings_valid_json(tmp_path: Path):
    project = tmp_path / "test-proj"
    project.mkdir()
    with patch("arasul_tui.core.platform.get_platform", return_value=_mock_platform()):
        scaffold_defaults(project, "test-proj")

    settings = json.loads((project / ".claude" / "settings.json").read_text())
    assert "permissions" in settings
    assert "deny" in settings["permissions"]


def test_scaffold_defaults_skip_claude_md(tmp_path: Path):
    project = tmp_path / "template-proj"
    project.mkdir()
    with patch("arasul_tui.core.platform.get_platform", return_value=_mock_platform()):
        scaffold_defaults(project, "template-proj", skip_claude_md=True)

    assert not (project / "CLAUDE.md").exists()
    assert (project / ".claude" / "settings.json").is_file()


def test_scaffold_defaults_idempotent(tmp_path: Path):
    project = tmp_path / "twice"
    project.mkdir()
    with patch("arasul_tui.core.platform.get_platform", return_value=_mock_platform()):
        scaffold_defaults(project, "twice")
        # Modify settings to prove it's not overwritten
        settings_path = project / ".claude" / "settings.json"
        settings_path.write_text('{"custom": true}')
        scaffold_defaults(project, "twice")

    # Settings should still be custom (not overwritten)
    assert json.loads(settings_path.read_text()) == {"custom": True}


def test_scaffold_clone_defaults_no_overwrite(tmp_path: Path):
    """Clone merge: existing files are never overwritten."""
    project = tmp_path / "cloned-repo"
    project.mkdir()

    # Simulate repo that already has .claude/ and CLAUDE.md
    (project / ".claude").mkdir()
    (project / ".claude" / "settings.json").write_text('{"repo": "original"}')
    (project / "CLAUDE.md").write_text("# Repo Author's CLAUDE.md\n")
    (project / "docs").mkdir()

    with patch("arasul_tui.core.platform.get_platform", return_value=_mock_platform()):
        scaffold_clone_defaults(project, "cloned-repo")

    # Existing files preserved
    assert json.loads((project / ".claude" / "settings.json").read_text()) == {"repo": "original"}
    assert "Repo Author" in (project / "CLAUDE.md").read_text()

    # Missing dirs created
    assert (project / ".claude" / "commands").is_dir()
    assert (project / ".claude" / "agents").is_dir()


def test_scaffold_clone_adds_missing_claude_md(tmp_path: Path):
    """Clone merge: CLAUDE.md created if repo doesn't have one."""
    project = tmp_path / "no-claude-repo"
    project.mkdir()

    with patch("arasul_tui.core.platform.get_platform", return_value=_mock_platform()):
        scaffold_clone_defaults(project, "no-claude-repo")

    assert (project / "CLAUDE.md").is_file()
    assert "no-claude-repo" in (project / "CLAUDE.md").read_text()


def test_scaffold_clone_adds_missing_settings(tmp_path: Path):
    """Clone merge: settings.json created if repo has .claude/ but no settings."""
    project = tmp_path / "partial-repo"
    project.mkdir()
    (project / ".claude").mkdir()
    # .claude/ exists but no settings.json

    with patch("arasul_tui.core.platform.get_platform", return_value=_mock_platform()):
        scaffold_clone_defaults(project, "partial-repo")

    assert (project / ".claude" / "settings.json").is_file()
    settings = json.loads((project / ".claude" / "settings.json").read_text())
    assert "permissions" in settings


def test_scaffold_docs_not_overwritten(tmp_path: Path):
    """Existing docs files are never overwritten."""
    project = tmp_path / "has-docs"
    project.mkdir()
    (project / "docs").mkdir()
    (project / "docs" / "tasks.md").write_text("# My custom tasks\n")

    with patch("arasul_tui.core.platform.get_platform", return_value=_mock_platform()):
        scaffold_defaults(project, "has-docs")

    # Existing file preserved
    assert "My custom tasks" in (project / "docs" / "tasks.md").read_text()
    # Missing files still created
    assert (project / "docs" / "lessons.md").exists()


def test_starter_claude_md_has_self_learning_block():
    """Self-learning block includes docs references for automatic tracking."""
    with patch("arasul_tui.core.platform.get_platform", return_value=_mock_platform()):
        md = _starter_claude_md("test-proj")
    assert "docs/tasks.md" in md
    assert "docs/lessons.md" in md
    assert "docs/decisions.md" in md
    assert "docs/changelog.md" in md
    assert "## Rules" in md
