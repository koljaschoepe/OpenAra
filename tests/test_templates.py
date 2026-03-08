"""Tests for the template engine (core/templates.py).

Strategy: Template properties are tested via parametrize to avoid repetition.
CLAUDE.md and .env generation verify platform-aware content rendering.
Scaffolding tests use real temp directories for file I/O confidence.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from arasul_tui.core.platform import Platform
from arasul_tui.core.templates import (
    TEMPLATES,
    TemplateConfig,
    generate_claude_md,
    generate_dotenv,
    get_template,
    is_miniforge_installed,
    list_available_templates,
    scaffold_project,
)
from tests.conftest import make_platform, mock_platform

# ---------------------------------------------------------------------------
# Platform helpers (using conftest factories)
# ---------------------------------------------------------------------------


def _jetson(mount: Path = Path("/mnt/nvme")) -> Platform:
    return make_platform(
        name="jetson",
        model="NVIDIA Jetson Orin Nano Super",
        arch="aarch64",
        gpu_type="nvidia",
        has_cuda=True,
        cuda_version="12.6",
        storage_type="nvme",
        storage_mount=mount,
        storage_device="/dev/nvme0n1",
        has_nvidia_runtime=True,
    )


def _rpi(mount: Path = Path("/home/pi")) -> Platform:
    return make_platform(
        name="raspberry_pi",
        model="Raspberry Pi 5 Model B Rev 1.0",
        arch="aarch64",
        storage_mount=mount,
    )


# ---------------------------------------------------------------------------
# Template registry
# ---------------------------------------------------------------------------


def test_all_templates_registered():
    """All 5 expected templates exist in the registry."""
    assert set(TEMPLATES.keys()) == {"python-gpu", "vision", "api", "notebook", "webapp"}


def test_get_template_nonexistent():
    """Unknown template name returns None."""
    assert get_template("nonexistent") is None


# ---------------------------------------------------------------------------
# Template properties (parametrized)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,expected",
    [
        pytest.param("python-gpu", True, id="python-gpu-requires-cuda"),
        pytest.param("vision", True, id="vision-requires-cuda"),
        pytest.param("api", True, id="api-requires-cuda"),
        pytest.param("notebook", False, id="notebook-no-cuda"),
        pytest.param("webapp", False, id="webapp-no-cuda"),
    ],
)
def test_template_requires_cuda(name: str, expected: bool):
    """GPU templates require CUDA; non-GPU templates do not."""
    assert get_template(name).requires_cuda is expected


@pytest.mark.parametrize(
    "name,expected",
    [
        pytest.param("vision", True, id="vision-has-docker"),
        pytest.param("api", True, id="api-has-docker"),
        pytest.param("webapp", True, id="webapp-has-docker"),
        pytest.param("notebook", False, id="notebook-no-docker"),
        pytest.param("python-gpu", False, id="python-gpu-no-docker"),
    ],
)
def test_template_has_docker(name: str, expected: bool):
    """Docker-based templates are flagged correctly."""
    assert get_template(name).has_docker is expected


def test_python_gpu_has_nvidia_index():
    """python-gpu template points to NVIDIA PyPI index for ARM wheels."""
    t = get_template("python-gpu")
    assert t.pip_extra_index is not None
    assert "nvidia" in t.pip_extra_index


# ---------------------------------------------------------------------------
# Template availability (platform-dependent)
# ---------------------------------------------------------------------------


def test_all_templates_available_on_jetson():
    """Jetson with CUDA sees all 5 templates."""
    with mock_platform(_jetson()):
        available = list_available_templates()
    assert len(available) == 5


def test_only_non_cuda_templates_on_rpi():
    """RPi without CUDA only sees notebook and webapp."""
    with mock_platform(_rpi()):
        available = list_available_templates()
    names = [t.name for t in available]
    assert len(available) == 2
    assert "notebook" in names
    assert "webapp" in names


# ---------------------------------------------------------------------------
# CLAUDE.md generation
# ---------------------------------------------------------------------------


def test_claude_md_contains_project_and_platform():
    """Generated CLAUDE.md includes project name and platform details."""
    t = get_template("python-gpu")
    with mock_platform(_jetson()):
        content = generate_claude_md("my-model", t)
    assert "my-model" in content
    assert "Jetson Orin Nano" in content
    assert "CUDA 12.6" in content


def test_claude_md_all_templates_include_basics():
    """Every template generates CLAUDE.md with project name and ARM64."""
    with mock_platform(_jetson()):
        for name, tpl in TEMPLATES.items():
            content = generate_claude_md(f"test-{name}", tpl)
            assert f"test-{name}" in content
            assert "ARM64" in content


def test_claude_md_rpi_no_cuda():
    """RPi CLAUDE.md mentions Raspberry Pi but not CUDA."""
    t = get_template("notebook")
    with mock_platform(_rpi()):
        content = generate_claude_md("research", t)
    assert "Raspberry Pi 5" in content
    assert "CUDA" not in content


def test_claude_md_jetson_gpu_hints():
    """Jetson CLAUDE.md includes GPU-specific instructions."""
    with mock_platform(_jetson()):
        # notebook template mentions GPU availability
        nb = generate_claude_md("research", get_template("notebook"))
        assert "GPU available" in nb
        # api template mentions nvidia runtime
        api = generate_claude_md("svc", get_template("api"))
        assert "--runtime=nvidia" in api


def test_claude_md_rpi_no_gpu_hints():
    """RPi CLAUDE.md omits GPU and nvidia runtime references."""
    with mock_platform(_rpi()):
        nb = generate_claude_md("research", get_template("notebook"))
        assert "GPU available" not in nb
        api = generate_claude_md("svc", get_template("api"))
        assert "--runtime=nvidia" not in api


def test_claude_md_uses_storage_paths():
    """CLAUDE.md env paths reflect the platform's storage mount."""
    with mock_platform(_jetson()):
        content = generate_claude_md("research", get_template("notebook"))
    assert "/mnt/nvme/" in content


def test_claude_md_has_self_learning_block():
    """Every template CLAUDE.md includes the self-learning section."""
    with mock_platform(_jetson()):
        for name, tpl in TEMPLATES.items():
            content = generate_claude_md(f"test-{name}", tpl)
            assert "Self-Learning" in content, f"{name} missing Self-Learning"
            assert "docs/tasks.md" in content, f"{name} missing tasks ref"
            assert "## Rules" in content, f"{name} missing Rules section"


def test_claude_md_under_200_lines():
    """Template CLAUDE.md files should stay under 200 lines."""
    with mock_platform(_jetson()):
        for name, tpl in TEMPLATES.items():
            content = generate_claude_md(f"test-{name}", tpl)
            line_count = len(content.splitlines())
            assert line_count < 200, f"{name} CLAUDE.md is {line_count} lines (max 200)"


# ---------------------------------------------------------------------------
# .env generation (parametrized)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "template_name,expected_var",
    [
        pytest.param("webapp", "POSTGRES_DB=", id="webapp-has-postgres"),
        pytest.param("api", "API_PORT=8000", id="api-has-port"),
        pytest.param("notebook", "JUPYTER_PORT=8888", id="notebook-has-jupyter"),
        pytest.param("python-gpu", "DEVICE=cuda", id="gpu-has-device"),
    ],
)
def test_generate_dotenv(template_name: str, expected_var: str):
    """Each template's .env contains its key configuration variable."""
    t = get_template(template_name)
    content = generate_dotenv("test-proj", t)
    assert expected_var in content


def test_generate_dotenv_unique_secrets():
    """Secrets are randomized — two generations produce different passwords."""
    t = get_template("webapp")
    env1 = generate_dotenv("app1", t)
    env2 = generate_dotenv("app2", t)
    pw1 = [line for line in env1.splitlines() if "POSTGRES_PASSWORD=" in line][0]
    pw2 = [line for line in env2.splitlines() if "POSTGRES_PASSWORD=" in line][0]
    assert pw1 != pw2


# ---------------------------------------------------------------------------
# Miniforge check
# ---------------------------------------------------------------------------


def test_miniforge_not_installed():
    """Returns False when conda binary doesn't exist."""
    with patch("arasul_tui.core.templates._conda_bin", return_value=Path("/nonexistent/conda")):
        assert is_miniforge_installed() is False


def test_miniforge_installed(tmp_path: Path):
    """Returns True when conda binary exists on disk."""
    conda = tmp_path / "conda"
    conda.write_text("#!/bin/sh\n")
    with patch("arasul_tui.core.templates._conda_bin", return_value=conda):
        assert is_miniforge_installed() is True


# ---------------------------------------------------------------------------
# Project scaffolding (real file I/O)
# ---------------------------------------------------------------------------


def test_scaffold_creates_essential_files(tmp_path: Path):
    """Scaffolding creates CLAUDE.md, .env, and .gitignore."""
    t = get_template("api")
    project_dir = tmp_path / "my-api"
    project_dir.mkdir()

    with mock_platform(_jetson()):
        ok, msg = scaffold_project(project_dir, "my-api", t)

    assert ok is True
    assert (project_dir / "CLAUDE.md").exists()
    assert (project_dir / ".env").exists()
    assert (project_dir / ".gitignore").exists()
    assert "my-api" in (project_dir / "CLAUDE.md").read_text()
    assert "API_PORT" in (project_dir / ".env").read_text()
    assert "__pycache__/" in (project_dir / ".gitignore").read_text()


def test_scaffold_copies_starter_files(tmp_path: Path):
    """Starter files from the template directory are copied into the project."""
    t = TemplateConfig(
        name="test-tpl",
        label="Test",
        description="test",
        starter_files=["hello.py"],
    )
    tpl_dir = tmp_path / "templates" / "test-tpl"
    tpl_dir.mkdir(parents=True)
    (tpl_dir / "hello.py").write_text("print('hello')\n")

    project_dir = tmp_path / "my-proj"
    project_dir.mkdir()

    with (
        patch("arasul_tui.core.templates.TEMPLATE_DIR", tmp_path / "templates"),
        mock_platform(_jetson()),
    ):
        ok, msg = scaffold_project(project_dir, "my-proj", t)

    assert ok is True
    assert (project_dir / "hello.py").read_text() == "print('hello')\n"


def test_scaffold_creates_nested_dirs(tmp_path: Path):
    """Starter files in subdirectories get their parent dirs created."""
    t = TemplateConfig(
        name="nested-tpl",
        label="Nested",
        description="test",
        starter_files=["sub/file.py"],
    )
    tpl_dir = tmp_path / "templates" / "nested-tpl" / "sub"
    tpl_dir.mkdir(parents=True)
    (tpl_dir / "file.py").write_text("# nested\n")

    project_dir = tmp_path / "proj"
    project_dir.mkdir()

    with (
        patch("arasul_tui.core.templates.TEMPLATE_DIR", tmp_path / "templates"),
        mock_platform(_jetson()),
    ):
        ok, _ = scaffold_project(project_dir, "proj", t)

    assert ok
    assert (project_dir / "sub" / "file.py").exists()
