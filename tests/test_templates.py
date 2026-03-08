"""Tests for the template engine (core/templates.py)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from arasul_tui.core.platform import GpuInfo, Platform, StorageInfo
from arasul_tui.core.templates import (
    TEMPLATES,
    TemplateConfig,
    generate_claude_md,
    generate_dotenv,
    get_template,
    is_miniforge_installed,
    list_available_templates,
    list_templates,
    scaffold_project,
)

# ---------------------------------------------------------------------------
# Mock platform helpers
# ---------------------------------------------------------------------------


def _jetson_platform(mount: Path = Path("/mnt/nvme")) -> Platform:
    return Platform(
        name="jetson",
        model="NVIDIA Jetson Orin Nano Super",
        arch="aarch64",
        ram_mb=8192,
        gpu=GpuInfo(type="nvidia", has_cuda=True, cuda_version="12.6"),
        storage=StorageInfo(type="nvme", mount=mount, device="/dev/nvme0n1"),
        has_docker=True,
        has_nvidia_runtime=True,
    )


def _rpi_platform(mount: Path = Path("/home/pi")) -> Platform:
    return Platform(
        name="raspberry_pi",
        model="Raspberry Pi 5 Model B Rev 1.0",
        arch="aarch64",
        ram_mb=8192,
        gpu=GpuInfo(type="none", has_cuda=False, cuda_version=""),
        storage=StorageInfo(type="sd_only", mount=mount, device=""),
        has_docker=True,
        has_nvidia_runtime=False,
    )


def _mock_platform(p: Platform):
    return patch("arasul_tui.core.platform.get_platform", return_value=p)


# ---------------------------------------------------------------------------
# Template registry
# ---------------------------------------------------------------------------


def test_list_templates():
    templates = list_templates()
    assert len(templates) == 5
    names = [t.name for t in templates]
    assert "python-gpu" in names
    assert "vision" in names
    assert "api" in names
    assert "notebook" in names
    assert "webapp" in names


def test_get_template_existing():
    t = get_template("python-gpu")
    assert t is not None
    assert t.name == "python-gpu"
    assert t.label == "Python + GPU"


def test_get_template_nonexistent():
    assert get_template("nonexistent") is None


def test_template_config_defaults():
    t = TemplateConfig(name="test", label="Test", description="Test template")
    assert t.python_version == "3.10"
    assert t.has_docker is False
    assert t.has_dotenv is True
    assert t.conda_packages == []
    assert t.pip_packages == []
    assert t.starter_files == []
    assert t.requires_cuda is False


def test_python_gpu_has_nvidia_index():
    t = get_template("python-gpu")
    assert t.pip_extra_index is not None
    assert "nvidia" in t.pip_extra_index


def test_python_gpu_requires_cuda():
    t = get_template("python-gpu")
    assert t.requires_cuda is True


def test_vision_requires_cuda():
    t = get_template("vision")
    assert t.requires_cuda is True


def test_api_requires_cuda():
    t = get_template("api")
    assert t.requires_cuda is True


def test_vision_has_docker():
    t = get_template("vision")
    assert t.has_docker is True


def test_api_has_docker():
    t = get_template("api")
    assert t.has_docker is True


def test_webapp_has_docker():
    t = get_template("webapp")
    assert t.has_docker is True


def test_notebook_no_docker():
    t = get_template("notebook")
    assert t.has_docker is False


# ---------------------------------------------------------------------------
# Template availability
# ---------------------------------------------------------------------------


def test_list_available_jetson():
    with _mock_platform(_jetson_platform()):
        available = list_available_templates()
    names = [t.name for t in available]
    assert len(available) == 5
    assert "python-gpu" in names
    assert "vision" in names


def test_list_available_rpi():
    with _mock_platform(_rpi_platform()):
        available = list_available_templates()
    names = [t.name for t in available]
    assert len(available) == 2
    assert "python-gpu" not in names
    assert "vision" not in names
    assert "api" not in names
    assert "notebook" in names
    assert "webapp" in names


# ---------------------------------------------------------------------------
# CLAUDE.md generation
# ---------------------------------------------------------------------------


def test_generate_claude_md_python_gpu():
    t = get_template("python-gpu")
    with _mock_platform(_jetson_platform()):
        content = generate_claude_md("my-model", t)
    assert "my-model" in content
    assert "Jetson Orin Nano" in content
    assert "CUDA 12.6" in content
    assert "PyTorch" in content
    assert "/mnt/nvme/envs/my-model" in content


def test_generate_claude_md_webapp():
    t = get_template("webapp")
    with _mock_platform(_jetson_platform()):
        content = generate_claude_md("my-app", t)
    assert "FastAPI" in content
    assert "PostgreSQL" in content
    assert "/expose" in content


def test_generate_claude_md_notebook():
    t = get_template("notebook")
    with _mock_platform(_jetson_platform()):
        content = generate_claude_md("research", t)
    assert "JupyterLab" in content
    assert "ssh -L 8888" in content


def test_generate_claude_md_all_templates():
    with _mock_platform(_jetson_platform()):
        for name, tpl in TEMPLATES.items():
            content = generate_claude_md(f"test-{name}", tpl)
            assert f"test-{name}" in content
            assert "ARM64" in content


def test_generate_claude_md_rpi_header():
    t = get_template("notebook")
    with _mock_platform(_rpi_platform()):
        content = generate_claude_md("research", t)
    assert "Raspberry Pi 5" in content
    assert "ARM64" in content
    assert "CUDA" not in content


def test_generate_claude_md_rpi_env_paths():
    t = get_template("api")
    with _mock_platform(_rpi_platform()):
        content = generate_claude_md("my-api", t)
    assert "/home/pi/envs/my-api" in content
    assert "/home/pi/miniforge3/" in content


def test_generate_claude_md_notebook_no_gpu_on_rpi():
    t = get_template("notebook")
    with _mock_platform(_rpi_platform()):
        content = generate_claude_md("research", t)
    assert "GPU available" not in content


def test_generate_claude_md_notebook_gpu_on_jetson():
    t = get_template("notebook")
    with _mock_platform(_jetson_platform()):
        content = generate_claude_md("research", t)
    assert "GPU available" in content


def test_generate_claude_md_notebook_storage_path():
    t = get_template("notebook")
    with _mock_platform(_jetson_platform()):
        content = generate_claude_md("research", t)
    assert "/mnt/nvme/" in content
    assert "Save large datasets" in content


def test_generate_claude_md_api_nvidia_on_jetson():
    t = get_template("api")
    with _mock_platform(_jetson_platform()):
        content = generate_claude_md("svc", t)
    assert "--runtime=nvidia" in content


def test_generate_claude_md_api_no_nvidia_on_rpi():
    t = get_template("api")
    with _mock_platform(_rpi_platform()):
        content = generate_claude_md("svc", t)
    assert "--runtime=nvidia" not in content


# ---------------------------------------------------------------------------
# .env generation
# ---------------------------------------------------------------------------


def test_generate_dotenv_webapp():
    t = get_template("webapp")
    content = generate_dotenv("my-app", t)
    assert "POSTGRES_DB=my_app" in content
    assert "POSTGRES_PASSWORD=" in content
    assert "SECRET_KEY=" in content
    assert "DATABASE_URL=" in content


def test_generate_dotenv_api():
    t = get_template("api")
    content = generate_dotenv("my-api", t)
    assert "API_PORT=8000" in content


def test_generate_dotenv_notebook():
    t = get_template("notebook")
    content = generate_dotenv("research", t)
    assert "JUPYTER_PORT=8888" in content
    assert "JUPYTER_TOKEN=" in content


def test_generate_dotenv_python_gpu():
    t = get_template("python-gpu")
    content = generate_dotenv("trainer", t)
    assert "DEVICE=cuda" in content


def test_generate_dotenv_unique_secrets():
    t = get_template("webapp")
    env1 = generate_dotenv("app1", t)
    env2 = generate_dotenv("app2", t)
    # Secrets should be different each time
    pw1 = [line for line in env1.splitlines() if "POSTGRES_PASSWORD=" in line][0]
    pw2 = [line for line in env2.splitlines() if "POSTGRES_PASSWORD=" in line][0]
    assert pw1 != pw2


# ---------------------------------------------------------------------------
# Miniforge check
# ---------------------------------------------------------------------------


def test_is_miniforge_installed_false():
    with patch("arasul_tui.core.templates._conda_bin", return_value=Path("/nonexistent/conda")):
        assert is_miniforge_installed() is False


def test_is_miniforge_installed_true(tmp_path: Path):
    conda = tmp_path / "conda"
    conda.write_text("#!/bin/sh\n")
    with patch("arasul_tui.core.templates._conda_bin", return_value=conda):
        assert is_miniforge_installed() is True


# ---------------------------------------------------------------------------
# Project scaffolding
# ---------------------------------------------------------------------------


def test_scaffold_creates_claude_md(tmp_path: Path):
    t = get_template("python-gpu")
    project_dir = tmp_path / "my-project"
    project_dir.mkdir()

    with _mock_platform(_jetson_platform()):
        ok, msg = scaffold_project(project_dir, "my-project", t)
    assert ok is True
    assert (project_dir / "CLAUDE.md").exists()

    content = (project_dir / "CLAUDE.md").read_text()
    assert "my-project" in content


def test_scaffold_creates_dotenv(tmp_path: Path):
    t = get_template("api")
    project_dir = tmp_path / "my-api"
    project_dir.mkdir()

    with _mock_platform(_jetson_platform()):
        scaffold_project(project_dir, "my-api", t)
    assert (project_dir / ".env").exists()

    content = (project_dir / ".env").read_text()
    assert "API_PORT" in content


def test_scaffold_creates_gitignore(tmp_path: Path):
    t = get_template("python-gpu")
    project_dir = tmp_path / "proj"
    project_dir.mkdir()

    with _mock_platform(_jetson_platform()):
        scaffold_project(project_dir, "proj", t)
    assert (project_dir / ".gitignore").exists()

    content = (project_dir / ".gitignore").read_text()
    assert ".env" in content
    assert "__pycache__/" in content


def test_scaffold_copies_starter_files(tmp_path: Path):
    # Create a fake template source
    t = TemplateConfig(
        name="test-tpl",
        label="Test",
        description="test",
        starter_files=["hello.py"],
    )

    # Create template source dir with the file
    tpl_dir = tmp_path / "templates" / "test-tpl"
    tpl_dir.mkdir(parents=True)
    (tpl_dir / "hello.py").write_text("print('hello')\n")

    project_dir = tmp_path / "my-proj"
    project_dir.mkdir()

    with (
        patch("arasul_tui.core.templates.TEMPLATE_DIR", tmp_path / "templates"),
        _mock_platform(_jetson_platform()),
    ):
        ok, msg = scaffold_project(project_dir, "my-proj", t)

    assert ok is True
    assert (project_dir / "hello.py").exists()
    assert (project_dir / "hello.py").read_text() == "print('hello')\n"


def test_scaffold_creates_nested_dirs(tmp_path: Path):
    """Webapp template has backend/ subdirectory files."""
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
        _mock_platform(_jetson_platform()),
    ):
        ok, _ = scaffold_project(project_dir, "proj", t)

    assert ok
    assert (project_dir / "sub" / "file.py").exists()
