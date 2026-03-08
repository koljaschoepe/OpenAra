from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from arasul_tui.core.projects import (
    get_project,
    list_projects,
    load_registry,
    register_project,
    save_registry,
    unregister_project,
)


def test_load_empty_registry(tmp_path: Path):
    reg_path = tmp_path / "projects.yaml"
    with patch("arasul_tui.core.projects.REGISTRY_PATH", reg_path):
        reg = load_registry()
        assert reg == {"projects": []}
        assert reg_path.exists()


def test_register_and_list(tmp_path: Path):
    reg_path = tmp_path / "config" / "projects.yaml"
    with patch("arasul_tui.core.projects.REGISTRY_PATH", reg_path):
        record = register_project(name="test-proj", path=tmp_path / "test-proj")
        assert record.name == "test-proj"
        assert record.created_at != ""

        projects = list_projects()
        assert len(projects) == 1
        assert projects[0].name == "test-proj"


def test_register_updates_existing(tmp_path: Path):
    reg_path = tmp_path / "projects.yaml"
    with patch("arasul_tui.core.projects.REGISTRY_PATH", reg_path):
        register_project(name="proj", path=tmp_path / "old-path")
        register_project(name="proj", path=tmp_path / "new-path")

        projects = list_projects()
        assert len(projects) == 1
        assert projects[0].path == str(tmp_path / "new-path")


def test_get_project(tmp_path: Path):
    reg_path = tmp_path / "projects.yaml"
    with patch("arasul_tui.core.projects.REGISTRY_PATH", reg_path):
        register_project(name="alpha", path=tmp_path / "alpha")
        register_project(name="beta", path=tmp_path / "beta")

        assert get_project("alpha") is not None
        assert get_project("alpha").name == "alpha"
        assert get_project("nonexistent") is None


def test_unregister_project(tmp_path: Path):
    reg_path = tmp_path / "projects.yaml"
    with patch("arasul_tui.core.projects.REGISTRY_PATH", reg_path):
        register_project(name="to-delete", path=tmp_path / "to-delete")
        assert len(list_projects()) == 1

        result = unregister_project("to-delete")
        assert result is True
        assert len(list_projects()) == 0


def test_unregister_nonexistent(tmp_path: Path):
    reg_path = tmp_path / "projects.yaml"
    with patch("arasul_tui.core.projects.REGISTRY_PATH", reg_path):
        result = unregister_project("nonexistent")
        assert result is False


def test_save_and_load_roundtrip(tmp_path: Path):
    reg_path = tmp_path / "projects.yaml"
    with patch("arasul_tui.core.projects.REGISTRY_PATH", reg_path):
        reg = {"projects": [{"name": "test", "path": "/tmp/test"}]}
        save_registry(reg)
        loaded = load_registry()
        assert loaded["projects"][0]["name"] == "test"


def test_corrupt_yaml_handled(tmp_path: Path):
    reg_path = tmp_path / "projects.yaml"
    reg_path.parent.mkdir(parents=True, exist_ok=True)
    reg_path.write_text("not: valid: yaml: [", encoding="utf-8")
    with patch("arasul_tui.core.projects.REGISTRY_PATH", reg_path):
        # Should not crash
        reg = load_registry()
        # yaml.safe_load may return partial data or None
        assert isinstance(reg, dict)


def test_list_projects_filters_invalid(tmp_path: Path):
    reg_path = tmp_path / "projects.yaml"
    with patch("arasul_tui.core.projects.REGISTRY_PATH", reg_path):
        reg = {
            "projects": [
                {"name": "", "path": "/tmp/test"},
                {"name": "valid", "path": ""},
                {"name": "good", "path": "/tmp/good"},
            ]
        }
        save_registry(reg)
        projects = list_projects()
        assert len(projects) == 1
        assert projects[0].name == "good"
