"""Template engine for GPU-ready project scaffolding.

Manages template registry, conda environment creation, CLAUDE.md generation,
and starter code deployment. Miniforge3 is lazily installed on first use.
"""

from __future__ import annotations

import os
import secrets
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

TEMPLATE_DIR = Path(__file__).parent.parent.parent / "config" / "templates"


def _storage_mount() -> Path:
    from arasul_tui.core.platform import get_platform

    return get_platform().storage.mount


def _miniforge_dir() -> Path:
    return _storage_mount() / "miniforge3"


def _conda_bin() -> Path:
    return _miniforge_dir() / "bin" / "conda"


def _envs_dir() -> Path:
    return _storage_mount() / "envs"


# ---------------------------------------------------------------------------
# Template definitions
# ---------------------------------------------------------------------------


@dataclass
class TemplateConfig:
    name: str
    label: str
    description: str
    conda_packages: list[str] = field(default_factory=list)
    pip_packages: list[str] = field(default_factory=list)
    pip_extra_index: str | None = None
    python_version: str = "3.10"
    has_docker: bool = False
    has_dotenv: bool = True
    starter_files: list[str] = field(default_factory=list)
    requires_cuda: bool = False


TEMPLATES: dict[str, TemplateConfig] = {
    "python-gpu": TemplateConfig(
        name="python-gpu",
        label="Python + GPU",
        description="PyTorch + CUDA for ML training, inference, GPU computing",
        conda_packages=["numpy", "scipy"],
        pip_packages=["torch", "torchvision", "torchaudio"],
        pip_extra_index="https://developer.download.nvidia.com/compute/redist/jp/v61",
        starter_files=["main.py", "requirements.txt"],
        requires_cuda=True,
    ),
    "vision": TemplateConfig(
        name="vision",
        label="Computer Vision",
        description="OpenCV + YOLO11 + torchvision for object detection and video analysis",
        conda_packages=["numpy"],
        pip_packages=["torch", "torchvision", "opencv-python-headless", "ultralytics"],
        pip_extra_index="https://developer.download.nvidia.com/compute/redist/jp/v61",
        has_docker=True,
        starter_files=["detect.py", "requirements.txt", "docker-compose.yml"],
        requires_cuda=True,
    ),
    "api": TemplateConfig(
        name="api",
        label="Inference API",
        description="FastAPI + PyTorch for model inference REST endpoints",
        conda_packages=["numpy"],
        pip_packages=["torch", "fastapi", "uvicorn[standard]"],
        pip_extra_index="https://developer.download.nvidia.com/compute/redist/jp/v61",
        has_docker=True,
        starter_files=["app.py", "requirements.txt", "Dockerfile", "docker-compose.yml", "Caddyfile"],
        requires_cuda=True,
    ),
    "notebook": TemplateConfig(
        name="notebook",
        label="JupyterLab",
        description="JupyterLab + scientific stack for data analysis and research",
        conda_packages=["numpy", "pandas", "matplotlib", "scikit-learn", "seaborn"],
        pip_packages=["jupyterlab"],
        starter_files=["getting_started.ipynb", "requirements.txt"],
    ),
    "webapp": TemplateConfig(
        name="webapp",
        label="Full-Stack Web App",
        description="Next.js + FastAPI + PostgreSQL + Caddy for self-hosted apps",
        conda_packages=[],
        pip_packages=["fastapi", "uvicorn[standard]", "asyncpg", "sqlalchemy[asyncio]", "alembic"],
        has_docker=True,
        starter_files=[
            "docker-compose.yml",
            "Caddyfile",
            "backend/app.py",
            "backend/requirements.txt",
            "backend/Dockerfile",
        ],
    ),
}


def list_templates() -> list[TemplateConfig]:
    return list(TEMPLATES.values())


def list_available_templates() -> list[TemplateConfig]:
    """Return templates available on the current platform (filters by GPU)."""
    from arasul_tui.core.platform import get_platform

    p = get_platform()
    return [t for t in TEMPLATES.values() if not t.requires_cuda or p.gpu.has_cuda]


def get_template(name: str) -> TemplateConfig | None:
    return TEMPLATES.get(name)


# ---------------------------------------------------------------------------
# Miniforge3 management
# ---------------------------------------------------------------------------


def is_miniforge_installed() -> bool:
    cb = _conda_bin()
    return cb.exists() and cb.is_file()


def install_miniforge(on_progress: Any = None) -> tuple[bool, str]:
    """Install Miniforge3. Returns (success, message).

    This calls the setup script which handles download, install, and config.
    """
    script = Path(__file__).parent.parent.parent / "scripts" / "10-miniforge-setup.sh"
    if not script.exists():
        return False, f"Setup script not found: {script}"

    try:
        result = subprocess.run(
            ["sudo", str(script)],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode == 0:
            return True, "Miniforge3 installed successfully"
        return False, (result.stderr or result.stdout or "Unknown error").strip()
    except subprocess.TimeoutExpired:
        return False, "Installation timed out (5 min)"
    except OSError as exc:
        return False, str(exc)


# ---------------------------------------------------------------------------
# Conda environment management
# ---------------------------------------------------------------------------


def _run_conda(args: list[str], timeout: int = 600) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(_conda_bin())] + args,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def create_conda_env(
    project_name: str,
    template: TemplateConfig,
    on_progress: Any = None,
) -> tuple[bool, str]:
    """Create an isolated conda env for a project. Returns (success, message)."""
    env_path = _envs_dir() / project_name

    if env_path.exists():
        return False, f"Environment already exists: {env_path}"

    # Create env with Python
    try:
        result = _run_conda(
            [
                "create",
                "--prefix",
                str(env_path),
                f"python={template.python_version}",
                "-y",
                "-q",
            ]
        )
        if result.returncode != 0:
            return False, f"conda create failed: {(result.stderr or result.stdout or '').strip()}"
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, f"conda create failed: {exc}"

    # Install conda packages
    if template.conda_packages:
        try:
            result = _run_conda(
                [
                    "install",
                    "--prefix",
                    str(env_path),
                    "-y",
                    "-q",
                ]
                + template.conda_packages
            )
            if result.returncode != 0:
                return False, f"conda install failed: {(result.stderr or result.stdout or '').strip()}"
        except (subprocess.TimeoutExpired, OSError) as exc:
            return False, f"conda install failed: {exc}"

    # Install pip packages
    if template.pip_packages:
        pip_bin = env_path / "bin" / "pip"
        pip_cmd = [str(pip_bin), "install", "-q"] + template.pip_packages
        if template.pip_extra_index:
            pip_cmd += ["--extra-index-url", template.pip_extra_index]
        try:
            result = subprocess.run(
                pip_cmd,
                capture_output=True,
                text=True,
                timeout=600,
            )
            if result.returncode != 0:
                return False, f"pip install failed: {(result.stderr or result.stdout or '').strip()}"
        except (subprocess.TimeoutExpired, OSError) as exc:
            return False, f"pip install failed: {exc}"

    return True, str(env_path)


def remove_conda_env(project_name: str) -> tuple[bool, str]:
    """Remove a conda env. Returns (success, message)."""
    env_path = _envs_dir() / project_name
    if not env_path.exists():
        return True, "Environment does not exist"
    try:
        shutil.rmtree(env_path)
        return True, f"Removed {env_path}"
    except OSError as exc:
        return False, str(exc)


# ---------------------------------------------------------------------------
# CLAUDE.md generation
# ---------------------------------------------------------------------------


def _generate_header(project_name: str, python_version: str) -> str:
    """Build the CLAUDE.md hardware section from detected platform."""
    from arasul_tui.core.platform import get_platform

    p = get_platform()
    mount = p.storage.mount

    lines = [f"# {project_name} — Claude Code Context", "", "## Hardware"]

    if p.is_jetson:
        ram_gb = p.ram_mb // 1024 or 8
        cuda = p.gpu.cuda_version or "12.6"
        lines += [
            f"- **Device:** {p.model} ({ram_gb}GB shared RAM)",
            f"- **GPU:** CUDA {cuda}",
            "- **Arch:** ARM64 (aarch64)",
        ]
    elif p.is_raspberry_pi:
        ram_gb = p.ram_mb // 1024 or 4
        lines += [
            f"- **Device:** {p.model}",
            f"- **RAM:** {ram_gb}GB",
            "- **Arch:** ARM64 (aarch64)",
        ]
    else:
        arch_line = "- **Arch:** ARM64 (aarch64)" if p.arch == "aarch64" else f"- **Arch:** {p.arch}"
        lines += [
            f"- **Device:** {p.model}",
            f"- **RAM:** {p.ram_mb // 1024}GB",
            arch_line,
        ]

    lines += [
        "",
        "## Environment",
        f"- **Python:** {python_version} (Miniforge3 conda)",
        f"- **Env path:** {mount / 'envs' / project_name}/",
        f"- **Activate:** `source {mount / 'miniforge3' / 'bin' / 'activate'} {mount / 'envs' / project_name}`",
        "",
        "## Constraints",
    ]

    if p.is_jetson:
        ram_gb = p.ram_mb // 1024 or 8
        lines += [
            f"- {ram_gb}GB RAM shared between CPU and GPU — monitor memory usage",
            "- ARM64 — not all PyPI wheels available, prefer conda-forge",
            "- Docker images must be linux/arm64 or multi-arch",
        ]
    elif p.arch == "aarch64":
        lines += [
            "- ARM64 — not all PyPI wheels available, prefer conda-forge",
            "- Docker images must be linux/arm64 or multi-arch",
        ]
    else:
        lines += [
            "- Docker images should match system architecture",
        ]

    return "\n".join(lines) + "\n"


def _template_section(name: str) -> str:
    """Return the template-specific CLAUDE.md section, platform-aware."""
    from arasul_tui.core.platform import get_platform

    p = get_platform()
    mount = p.storage.mount
    cuda = p.gpu.cuda_version or "12.6"

    if name == "python-gpu":
        ram_gb = p.ram_mb // 1024 or 8
        gpu_avail = max(1, ram_gb - 3)  # rough estimate: ~3GB for system
        return f"""
## Stack
- PyTorch (NVIDIA Jetson wheels) + numpy + scipy
- CUDA {cuda} available at /usr/local/cuda-{cuda}/
- GPU memory shared with system — ~{gpu_avail}GB available for training

## PyTorch Notes
- Jetson wheels from NVIDIA index (not PyPI)
- Use `torch.cuda.is_available()` to verify GPU access
- Monitor GPU memory: `torch.cuda.mem_get_info()`
- For large models, use `torch.cuda.amp` for mixed precision
"""

    if name == "vision":
        return f"""
## Stack
- PyTorch + torchvision + OpenCV + YOLO11 (ultralytics)
- Docker Compose with `--runtime=nvidia` for GPU access
- CUDA {cuda} available at /usr/local/cuda-{cuda}/

## Vision Notes
- OpenCV headless build (no GUI) — use `cv2.imwrite()` to save results
- YOLO11: `from ultralytics import YOLO; model = YOLO('yolo11n.pt')`
- Camera: `/dev/video0` (USB) or CSI via GStreamer pipeline
- For real-time: target 720p or lower for good FPS on 1024 CUDA cores
"""

    if name == "api":
        if p.gpu.has_cuda:
            return """
## Stack
- FastAPI + Uvicorn + PyTorch
- Caddy reverse proxy with auto-HTTPS
- Docker Compose with `--runtime=nvidia`

## API Notes
- Health endpoint: GET /health
- Prediction endpoint: POST /predict
- Load model once at startup, not per-request
- Uvicorn workers: 1 (shared GPU memory)
- Caddy handles HTTPS termination
"""
        return """
## Stack
- FastAPI + Uvicorn
- Caddy reverse proxy with auto-HTTPS
- Docker Compose

## API Notes
- Health endpoint: GET /health
- Prediction endpoint: POST /predict
- Load model once at startup, not per-request
- Caddy handles HTTPS termination
"""

    if name == "notebook":
        gpu_line = "\n- GPU available in notebooks via PyTorch (if installed)" if p.gpu.has_cuda else ""
        return f"""
## Stack
- JupyterLab + numpy + pandas + matplotlib + scikit-learn + seaborn

## Access
- Start: `jupyter lab --no-browser --ip=0.0.0.0 --port=8888`
- SSH tunnel from your machine: `ssh -L 8888:localhost:8888 mydevice`
- Then open: http://localhost:8888

## Notes
- ~180MB RAM for JupyterLab server{gpu_line}
- Save large datasets to {mount}/, not project dir
"""

    if name == "webapp":
        return """
## Stack
- **Backend:** FastAPI + SQLAlchemy + asyncpg on port 8000
- **Database:** PostgreSQL 16 (Docker)
- **Proxy:** Caddy with auto-HTTPS

## Development
- Start all services: `docker compose up -d`
- Backend API docs: http://localhost:8000/docs
- Add a frontend: create a `frontend/` directory with your framework of choice

## Deployment
- Caddy handles HTTPS via Tailscale Funnel
- Use `/expose` in Arasul TUI to start public URL
- Database data persisted in Docker volume

## Environment Variables
- `.env` has auto-generated secrets — do NOT commit
- `DATABASE_URL` connects backend to PostgreSQL
- `SECRET_KEY` for session/JWT signing
"""

    return ""


def generate_claude_md(project_name: str, template: TemplateConfig) -> str:
    """Generate a project-specific CLAUDE.md with self-learning block."""
    from arasul_tui.core.scaffold import _self_learning_section

    content = _generate_header(project_name, template.python_version)
    section = _template_section(template.name)
    if section:
        content += section
    content += _self_learning_section()
    return content


# ---------------------------------------------------------------------------
# .env generation
# ---------------------------------------------------------------------------


def generate_dotenv(project_name: str, template: TemplateConfig) -> str:
    """Generate a .env file with auto-generated secrets."""
    lines = [
        f"# {project_name} environment variables",
        f"PROJECT_NAME={project_name}",
        "",
    ]

    if template.name == "webapp":
        db_password = secrets.token_urlsafe(24)
        db_name = project_name.replace("-", "_")
        lines += [
            "# Database",
            f"POSTGRES_DB={db_name}",
            "POSTGRES_USER=app",
            f"POSTGRES_PASSWORD={db_password}",
            f"DATABASE_URL=postgresql+asyncpg://app:{db_password}@db:5432/{db_name}",
            "",
            "# Security",
            f"SECRET_KEY={secrets.token_urlsafe(32)}",
            "",
            "# Ports",
            "BACKEND_PORT=8000",
        ]
    elif template.name == "api":
        lines += [
            "# API",
            "API_HOST=0.0.0.0",
            "API_PORT=8000",
            "MODEL_PATH=model.pt",
        ]
    elif template.name == "notebook":
        lines += [
            "# JupyterLab",
            "JUPYTER_PORT=8888",
            f"JUPYTER_TOKEN={secrets.token_urlsafe(16)}",
        ]
    else:
        lines += [
            "# Project",
            "DEVICE=cuda",
        ]

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Project scaffolding
# ---------------------------------------------------------------------------


def scaffold_project(
    project_dir: Path,
    project_name: str,
    template: TemplateConfig,
) -> tuple[bool, str]:
    """Copy template files and generate config files.

    Assumes project_dir already exists. Does NOT create conda env.
    Returns (success, message).
    """
    template_source = TEMPLATE_DIR / template.name

    # Copy starter files from template directory
    if template_source.exists():
        for rel_file in template.starter_files:
            src = template_source / rel_file
            dst = project_dir / rel_file
            if src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

    # Generate CLAUDE.md
    claude_md = generate_claude_md(project_name, template)
    (project_dir / "CLAUDE.md").write_text(claude_md)

    # Generate .env (restricted permissions — contains secrets)
    if template.has_dotenv:
        dotenv = generate_dotenv(project_name, template)
        env_path = project_dir / ".env"
        env_path.write_text(dotenv)
        os.chmod(str(env_path), 0o600)

    # Generate .gitignore
    gitignore_lines = [
        ".env",
        "__pycache__/",
        "*.pyc",
        ".ipynb_checkpoints/",
        "*.pt",
        "*.pth",
        "*.onnx",
        "node_modules/",
        ".next/",
    ]
    (project_dir / ".gitignore").write_text("\n".join(gitignore_lines) + "\n")

    return True, "Project scaffolded"
