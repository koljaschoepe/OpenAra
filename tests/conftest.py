from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from arasul_tui.core.cache import invalidate_all
from arasul_tui.core.platform import GpuInfo, Platform, StorageInfo
from arasul_tui.core.router import REGISTRY
from arasul_tui.core.state import TuiState


@pytest.fixture(autouse=True)
def _clear_caches():
    """Invalidate all cached shell results between tests."""
    invalidate_all()
    yield
    invalidate_all()


@pytest.fixture(autouse=True)
def _mock_console_width():
    """Ensure console.width returns a real int in tests (no terminal)."""
    with patch("arasul_tui.core.ui.output.console") as mock_console:
        mock_console.width = 100
        mock_console.print = lambda *a, **kw: None
        yield mock_console


@pytest.fixture
def tmp_project_root(tmp_path: Path) -> Path:
    """Provide a temporary project root directory."""
    root = tmp_path / "projects"
    root.mkdir()
    return root


@pytest.fixture
def state(tmp_project_root: Path) -> TuiState:
    """Provide a TuiState with a temporary project root and registry."""
    s = TuiState(registry=REGISTRY)
    s.project_root = tmp_project_root
    return s


@pytest.fixture
def state_with_projects(state: TuiState) -> TuiState:
    """Provide a TuiState with some test projects created."""
    for name in ["alpha", "beta", "gamma"]:
        (state.project_root / name).mkdir()
    return state


# ---------------------------------------------------------------------------
# Shared Platform factories (10.8)
# ---------------------------------------------------------------------------


def make_platform(
    name: str = "generic",
    model: str = "test-device",
    arch: str = "x86_64",
    ram_mb: int = 8192,
    gpu_type: str = "none",
    has_cuda: bool = False,
    cuda_version: str = "",
    storage_type: str = "sd_only",
    storage_mount: Path | None = None,
    storage_device: str = "",
    has_docker: bool = True,
    has_nvidia_runtime: bool = False,
) -> Platform:
    """Factory for creating test Platform instances."""
    return Platform(
        name=name,
        model=model,
        arch=arch,
        ram_mb=ram_mb,
        gpu=GpuInfo(type=gpu_type, has_cuda=has_cuda, cuda_version=cuda_version),
        storage=StorageInfo(
            type=storage_type,
            mount=storage_mount or Path.home(),
            device=storage_device,
        ),
        has_docker=has_docker,
        has_nvidia_runtime=has_nvidia_runtime,
    )


@pytest.fixture
def jetson_platform(tmp_path: Path) -> Platform:
    """Provide a Jetson platform for tests."""
    return make_platform(
        name="jetson",
        model="NVIDIA Jetson Orin Nano Super",
        arch="aarch64",
        gpu_type="nvidia",
        has_cuda=True,
        cuda_version="12.6",
        storage_type="nvme",
        storage_mount=tmp_path / "nvme",
        storage_device="/dev/nvme0n1",
        has_nvidia_runtime=True,
    )


@pytest.fixture
def rpi_platform(tmp_path: Path) -> Platform:
    """Provide a Raspberry Pi platform for tests."""
    return make_platform(
        name="raspberry_pi",
        model="Raspberry Pi 5 Model B Rev 1.0",
        arch="aarch64",
        storage_type="usb_ssd",
        storage_mount=tmp_path / "data",
        storage_device="/dev/sda",
    )


@pytest.fixture
def generic_platform(tmp_path: Path) -> Platform:
    """Provide a generic Linux platform for tests."""
    return make_platform(
        name="generic",
        model="my-server",
        arch="x86_64",
        ram_mb=16384,
        storage_mount=tmp_path / "home",
    )
