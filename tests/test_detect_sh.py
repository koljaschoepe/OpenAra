"""Tests for lib/detect.sh — shell-level hardware detection library.

Runs detect.sh functions via subprocess and validates output.
On CI (ubuntu-latest x86), these tests verify "generic" platform detection.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

DETECT_SH = Path(__file__).resolve().parent.parent / "lib" / "detect.sh"


def _run_fn(fn_name: str, env_override: dict[str, str] | None = None) -> str:
    """Source detect.sh and call a function, returning stdout."""
    env = os.environ.copy()
    if env_override:
        env.update(env_override)
    cmd = f'source "{DETECT_SH}" && {fn_name}'
    r = subprocess.run(
        ["bash", "-c", cmd],
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
    )
    return r.stdout.strip()


# ---------------------------------------------------------------------------
# detect_platform()
# ---------------------------------------------------------------------------


class TestDetectPlatform:
    def test_returns_valid_platform(self):
        result = _run_fn("detect_platform")
        assert result in ("jetson", "raspberry_pi", "generic")

    def test_generic_on_ci_or_macos(self):
        """On CI (ubuntu x86) or macOS dev, expect 'generic'."""
        import sys

        if sys.platform in ("linux", "darwin"):
            # If no Tegra or RPi hardware, should be generic
            tegra = Path("/etc/nv_tegra_release")
            dt_model = Path("/proc/device-tree/model")
            if not tegra.exists() and not (dt_model.exists()):
                assert _run_fn("detect_platform") == "generic"


# ---------------------------------------------------------------------------
# detect_model()
# ---------------------------------------------------------------------------


class TestDetectModel:
    def test_returns_nonempty(self):
        result = _run_fn("detect_model")
        assert len(result) > 0

    def test_returns_hostname_on_generic(self):
        """On generic systems without device-tree, returns hostname."""
        if not Path("/proc/device-tree/model").exists():
            import socket

            hostname = socket.gethostname()
            result = _run_fn("detect_model")
            assert result == hostname


# ---------------------------------------------------------------------------
# detect_arch()
# ---------------------------------------------------------------------------


def test_detect_arch():
    result = _run_fn("detect_arch")
    assert result in ("aarch64", "arm64", "x86_64", "armv7l", "i686")


# ---------------------------------------------------------------------------
# detect_gpu_type()
# ---------------------------------------------------------------------------


class TestDetectGpuType:
    def test_returns_valid_type(self):
        result = _run_fn("detect_gpu_type")
        assert result in ("nvidia", "none")

    def test_none_without_nvidia(self):
        """Without NVIDIA hardware, should return 'none'."""
        tegra = Path("/etc/nv_tegra_release")
        if not tegra.exists():
            # Check if nvidia-smi is available
            r = subprocess.run(["which", "nvidia-smi"], capture_output=True, text=True)
            if r.returncode != 0:
                assert _run_fn("detect_gpu_type") == "none"


# ---------------------------------------------------------------------------
# detect_ram_mb()
# ---------------------------------------------------------------------------


def test_detect_ram_mb():
    """RAM detection returns a positive integer string."""
    import sys

    if sys.platform == "linux":
        result = _run_fn("detect_ram_mb")
        assert result.isdigit()
        assert int(result) > 0


# ---------------------------------------------------------------------------
# detect_storage_type()
# ---------------------------------------------------------------------------


class TestDetectStorageType:
    def test_returns_valid_type(self):
        result = _run_fn("detect_storage_type")
        assert result in ("nvme", "usb_ssd", "sd_only")


# ---------------------------------------------------------------------------
# detect_storage_mount() — environment override tests
# ---------------------------------------------------------------------------


class TestDetectStorageMount:
    def test_honors_storage_mount_env(self):
        result = _run_fn("detect_storage_mount", env_override={"STORAGE_MOUNT": "/mnt/custom"})
        assert result == "/mnt/custom"

    def test_honors_legacy_nvme_mount_env(self):
        result = _run_fn("detect_storage_mount", env_override={"NVME_MOUNT": "/mnt/nvme"})
        assert result == "/mnt/nvme"

    def test_storage_mount_takes_precedence(self):
        result = _run_fn(
            "detect_storage_mount",
            env_override={
                "STORAGE_MOUNT": "/mnt/new",
                "NVME_MOUNT": "/mnt/old",
            },
        )
        assert result == "/mnt/new"


# ---------------------------------------------------------------------------
# Boolean helpers
# ---------------------------------------------------------------------------


class TestBooleanHelpers:
    def test_has_docker(self):
        """has_docker returns 0 (true) or 1 (false)."""
        cmd = f'source "{DETECT_SH}" && has_docker && echo "yes" || echo "no"'
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=10)
        result = r.stdout.strip()
        assert result in ("yes", "no")

    def test_has_nvidia_runtime(self):
        cmd = f'source "{DETECT_SH}" && has_nvidia_runtime && echo "yes" || echo "no"'
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=10)
        result = r.stdout.strip()
        assert result in ("yes", "no")


# ---------------------------------------------------------------------------
# print_hardware_summary()
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not Path("/proc/meminfo").exists(),
    reason="Requires /proc/meminfo (Linux only)",
)
def test_print_hardware_summary():
    """Summary prints something and exits cleanly."""
    result = _run_fn("print_hardware_summary")
    assert "Hardware detected:" in result
    assert "Device:" in result
    assert "RAM:" in result
    assert "Arch:" in result
