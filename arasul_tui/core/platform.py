"""Hardware detection and platform abstraction layer.

Detects the host platform (Jetson, Raspberry Pi, generic Linux) and provides
a singleton ``Platform`` object with hardware info used throughout the TUI.

Usage::

    from arasul_tui.core.platform import get_platform

    p = get_platform()
    print(p.model)           # "NVIDIA Jetson Orin Nano Super"
    print(p.project_root)    # Path("/mnt/nvme/projects")
    print(p.is_jetson)       # True
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GpuInfo:
    """GPU information. VideoCore on RPi is deliberately ignored."""

    type: str  # "nvidia" | "none"
    has_cuda: bool
    cuda_version: str  # e.g. "12.6" or ""

    @property
    def model(self) -> str:
        if self.type == "nvidia":
            return f"NVIDIA (CUDA {self.cuda_version})" if self.cuda_version else "NVIDIA"
        return ""


@dataclass(frozen=True)
class StorageInfo:
    """Detected storage configuration."""

    type: str  # "nvme" | "usb_ssd" | "sd_only"
    mount: Path  # e.g. /mnt/nvme, /mnt/data, or /home/user
    device: str  # e.g. "/dev/nvme0n1" or ""

    @property
    def is_external(self) -> bool:
        return self.type in ("nvme", "usb_ssd")


@dataclass(frozen=True)
class Platform:
    """Detected hardware platform — singleton via ``get_platform()``."""

    name: str  # "jetson" | "raspberry_pi" | "generic"
    model: str  # Full model string
    arch: str  # "aarch64" | "x86_64"
    ram_mb: int  # Total RAM in MB
    gpu: GpuInfo
    storage: StorageInfo
    has_docker: bool
    has_nvidia_runtime: bool

    @property
    def project_root(self) -> Path:
        return self.storage.mount / "projects"

    @property
    def is_jetson(self) -> bool:
        return self.name == "jetson"

    @property
    def is_raspberry_pi(self) -> bool:
        return self.name == "raspberry_pi"

    @property
    def display_name(self) -> str:
        """Short name for dashboard header."""
        if self.is_jetson:
            # Strip "NVIDIA " prefix if present for brevity
            m = self.model
            if m.startswith("NVIDIA "):
                m = m[7:]
            return m
        return self.model


# ---------------------------------------------------------------------------
# Detection helpers (thin wrappers around system queries)
# ---------------------------------------------------------------------------


def _read_file(path: str) -> str:
    """Read a file, stripping null bytes and whitespace. Returns '' on error."""
    try:
        return Path(path).read_text(errors="replace").replace("\x00", "").strip()
    except OSError:
        return ""


def _run(cmd: list[str], timeout: int = 5) -> str:
    """Run a command, return stdout stripped. Returns '' on error."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def detect_platform() -> str:
    """Detect platform type: 'jetson', 'raspberry_pi', or 'generic'."""
    # Jetson checks
    if Path("/etc/nv_tegra_release").exists():
        return "jetson"
    dpkg_out = _run(["dpkg", "-l", "nvidia-l4t-core"])
    if dpkg_out and any(line.startswith("ii ") for line in dpkg_out.splitlines()):
        return "jetson"
    compat = _read_file("/proc/device-tree/compatible")
    if "tegra" in compat.lower():
        return "jetson"

    # Raspberry Pi
    dt_model = _read_file("/proc/device-tree/model")
    if "raspberry pi" in dt_model.lower():
        return "raspberry_pi"

    return "generic"


def detect_model() -> str:
    """Full model string from device tree, e.g. 'Raspberry Pi 5 Model B Rev 1.0'."""
    dt = _read_file("/proc/device-tree/model")
    if dt:
        return dt
    return _run(["uname", "-n"]) or "Unknown"


def detect_arch() -> str:
    """CPU architecture: 'aarch64', 'x86_64', etc."""
    import platform as _platform

    return _platform.machine()


def detect_ram_mb() -> int:
    """Total RAM in megabytes."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) // 1024
    except OSError:
        pass
    # Fallback
    try:
        import os as _os

        pages = _os.sysconf("SC_PHYS_PAGES")
        page_size = _os.sysconf("SC_PAGE_SIZE")
        return (pages * page_size) // (1024 * 1024)
    except (ValueError, OSError):
        return 0


def detect_gpu() -> GpuInfo:
    """Detect GPU type and CUDA version."""
    gpu_type = "none"
    cuda_version = ""

    # NVIDIA via Tegra
    if Path("/etc/nv_tegra_release").exists() or shutil.which("nvidia-smi"):
        gpu_type = "nvidia"

    if gpu_type == "nvidia":
        cuda_version = _detect_cuda_version()

    return GpuInfo(type=gpu_type, has_cuda=gpu_type == "nvidia", cuda_version=cuda_version)


def _detect_cuda_version() -> str:
    """Try to find CUDA version string."""
    # Method 1: version.json (JetPack 6+)
    vj = Path("/usr/local/cuda/version.json")
    if vj.exists():
        try:
            import json

            data = json.loads(vj.read_text())
            return data["cuda"]["version"]
        except (json.JSONDecodeError, KeyError, OSError):
            pass
    # Method 2: nvcc
    out = _run(["nvcc", "--version"])
    if out:
        import re

        m = re.search(r"release (\d+\.\d+)", out)
        if m:
            return m.group(1)
    return ""


def detect_storage() -> StorageInfo:
    """Detect best available storage."""
    device = ""
    storage_type = "sd_only"
    mount = Path.home()

    # Check environment overrides (legacy support)
    env_mount = os.environ.get("STORAGE_MOUNT") or os.environ.get("NVME_MOUNT")
    if env_mount:
        p = Path(env_mount)
        # Detect actual type from mount's underlying device
        if p.exists():
            dev_path = _run(["findmnt", "-n", "-o", "SOURCE", str(p)])
            if dev_path:
                tran = _run(["lsblk", "-dno", "TRAN", dev_path.split("[")[0]])
                if tran == "nvme":
                    storage_type = "nvme"
                elif tran == "usb":
                    storage_type = "usb_ssd"
                else:
                    storage_type = "sd_only"
            elif "nvme" in env_mount.lower():
                storage_type = "nvme"
        return StorageInfo(type=storage_type, mount=p, device="")

    # Auto-detect via lsblk
    lsblk_out = _run(["lsblk", "-dno", "PATH,TRAN"])
    if lsblk_out:
        for line in lsblk_out.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                path, tran = parts[0], parts[1]
                if tran == "nvme":
                    device = path
                    storage_type = "nvme"
                    break
                if tran == "usb" and not device:
                    # Verify it's a disk, not a USB hub device
                    dtype = _run(["lsblk", "-dno", "TYPE", path])
                    if dtype == "disk":
                        device = path
                        storage_type = "usb_ssd"

    if device:
        # Check if already mounted
        mp = _run(["lsblk", "-nro", "MOUNTPOINT", device])
        lines = [ln for ln in mp.splitlines() if ln.strip()] if mp else []
        mount = Path(lines[0]) if lines else Path("/mnt/data")
    # else: sd_only, mount stays as home dir

    return StorageInfo(type=storage_type, mount=mount, device=device)


def detect_docker() -> tuple[bool, bool]:
    """Returns (has_docker, has_nvidia_runtime)."""
    has_docker = shutil.which("docker") is not None
    has_nvidia = False
    if has_docker:
        info = _run(["docker", "info"], timeout=2)
        has_nvidia = "nvidia" in info.lower() if info else False
    return has_docker, has_nvidia


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_platform_instance: Platform | None = None


def detect() -> Platform:
    """Run full hardware detection and return a new Platform instance."""
    name = detect_platform()
    model = detect_model()
    arch = detect_arch()
    ram_mb = detect_ram_mb()
    gpu = detect_gpu()
    storage = detect_storage()
    docker, nvidia_rt = detect_docker()

    return Platform(
        name=name,
        model=model,
        arch=arch,
        ram_mb=ram_mb,
        gpu=gpu,
        storage=storage,
        has_docker=docker,
        has_nvidia_runtime=nvidia_rt,
    )


def get_platform() -> Platform:
    """Return cached Platform singleton. Runs detection on first call."""
    global _platform_instance
    if _platform_instance is None:
        _platform_instance = detect()
    return _platform_instance


def reset_platform() -> None:
    """Clear cached platform (for testing)."""
    global _platform_instance
    _platform_instance = None
