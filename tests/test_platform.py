"""Tests for arasul_tui.core.platform — hardware detection layer.

Strategy: Each detect_*() function is tested with mocked /proc and /sys
files to simulate Jetson, RPi, and generic Linux. Full detect() integration
runs on the actual host to catch real-system regressions. Platform property
tests use conftest's make_platform() factory.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from arasul_tui.core.platform import (
    GpuInfo,
    Platform,
    StorageInfo,
    detect,
    detect_arch,
    detect_gpu,
    detect_model,
    detect_platform,
    detect_ram_mb,
    detect_storage,
    get_platform,
    reset_platform,
)
from tests.conftest import make_platform

# ---------------------------------------------------------------------------
# detect_platform()
# ---------------------------------------------------------------------------


class TestDetectPlatform:
    def test_jetson_via_tegra_release(self, tmp_path):
        tegra = tmp_path / "nv_tegra_release"
        tegra.write_text("# R36 (release)\n")
        with patch("arasul_tui.core.platform.Path") as MP:
            MP.return_value.exists.return_value = True
            assert detect_platform() == "jetson"

    def test_jetson_via_dpkg(self):
        with patch("arasul_tui.core.platform.Path") as MP:
            MP.return_value.exists.return_value = False
            with (
                patch("arasul_tui.core.platform._run", return_value="ii nvidia-l4t-core"),
                patch("arasul_tui.core.platform._read_file", return_value=""),
            ):
                assert detect_platform() == "jetson"

    def test_jetson_via_device_tree_compatible(self):
        with patch("arasul_tui.core.platform.Path") as MP:
            MP.return_value.exists.return_value = False
            with (
                patch("arasul_tui.core.platform._run", return_value=""),
                patch(
                    "arasul_tui.core.platform._read_file",
                    return_value="nvidia,tegra234",
                ),
            ):
                assert detect_platform() == "jetson"

    def test_raspberry_pi(self):
        with patch("arasul_tui.core.platform.Path") as MP:
            MP.return_value.exists.return_value = False
            with (
                patch("arasul_tui.core.platform._run", return_value=""),
                patch(
                    "arasul_tui.core.platform._read_file",
                    side_effect=lambda p: "Raspberry Pi 5 Model B Rev 1.0" if "model" in p else "",
                ),
            ):
                assert detect_platform() == "raspberry_pi"

    def test_generic_fallback(self):
        with patch("arasul_tui.core.platform.Path") as MP:
            MP.return_value.exists.return_value = False
            with (
                patch("arasul_tui.core.platform._run", return_value=""),
                patch("arasul_tui.core.platform._read_file", return_value=""),
            ):
                assert detect_platform() == "generic"


# ---------------------------------------------------------------------------
# detect_model()
# ---------------------------------------------------------------------------


class TestDetectModel:
    def test_from_device_tree(self):
        with patch(
            "arasul_tui.core.platform._read_file",
            return_value="NVIDIA Jetson Orin Nano Super",
        ):
            assert detect_model() == "NVIDIA Jetson Orin Nano Super"

    def test_fallback_to_uname(self):
        with (
            patch("arasul_tui.core.platform._read_file", return_value=""),
            patch("arasul_tui.core.platform._run", return_value="myhost"),
        ):
            assert detect_model() == "myhost"

    def test_fallback_unknown(self):
        with (
            patch("arasul_tui.core.platform._read_file", return_value=""),
            patch("arasul_tui.core.platform._run", return_value=""),
        ):
            assert detect_model() == "Unknown"


# ---------------------------------------------------------------------------
# detect_arch()
# ---------------------------------------------------------------------------


def test_detect_arch():
    """detect_arch returns current machine architecture."""
    import platform as _platform

    assert detect_arch() == _platform.machine()


# ---------------------------------------------------------------------------
# detect_ram_mb()
# ---------------------------------------------------------------------------


class TestDetectRamMb:
    def test_reads_meminfo(self, tmp_path):
        meminfo = tmp_path / "meminfo"
        meminfo.write_text("MemTotal:        8048576 kB\nMemFree:         4000000 kB\n")
        with patch("builtins.open", return_value=meminfo.open()):
            result = detect_ram_mb()
            assert result == 7859  # 8048576 // 1024

    def test_returns_nonzero_on_real_system(self):
        # On any real system, RAM should be > 0
        assert detect_ram_mb() > 0


# ---------------------------------------------------------------------------
# detect_gpu()
# ---------------------------------------------------------------------------


class TestDetectGpu:
    def test_nvidia_via_tegra(self):
        with patch("arasul_tui.core.platform.Path") as MP:
            MP.return_value.exists.return_value = True
            with patch("arasul_tui.core.platform._detect_cuda_version", return_value="12.6"):
                gpu = detect_gpu()
                assert gpu.type == "nvidia"
                assert gpu.has_cuda is True
                assert gpu.cuda_version == "12.6"

    def test_no_gpu(self):
        with patch("arasul_tui.core.platform.Path") as MP:
            MP.return_value.exists.return_value = False
            with patch("arasul_tui.core.platform.shutil") as mock_shutil:
                mock_shutil.which.return_value = None
                gpu = detect_gpu()
                assert gpu.type == "none"
                assert gpu.has_cuda is False
                assert gpu.cuda_version == ""


# ---------------------------------------------------------------------------
# detect_storage()
# ---------------------------------------------------------------------------


class TestDetectStorage:
    def test_env_override(self):
        with patch.dict("os.environ", {"STORAGE_MOUNT": "/mnt/custom"}):
            s = detect_storage()
            assert s.mount == Path("/mnt/custom")

    def test_legacy_nvme_mount_env(self):
        env = {"NVME_MOUNT": "/mnt/nvme"}
        with patch.dict("os.environ", env, clear=True):
            s = detect_storage()
            assert s.mount == Path("/mnt/nvme")

    def test_sd_only_fallback(self):
        with patch.dict("os.environ", {}, clear=True), patch("arasul_tui.core.platform._run", return_value=""):
            s = detect_storage()
            assert s.type == "sd_only"
            assert s.mount == Path.home()
            assert s.device == ""

    def test_nvme_detected(self):
        with (
            patch.dict("os.environ", {}, clear=True),
            patch(
                "arasul_tui.core.platform._run",
                side_effect=lambda cmd, **kw: {
                    ("lsblk", "-dno", "PATH,TRAN"): "/dev/nvme0n1 nvme",
                    ("lsblk", "-nro", "MOUNTPOINT", "/dev/nvme0n1"): "/mnt/nvme",
                }.get(tuple(cmd), ""),
            ),
        ):
            s = detect_storage()
            assert s.type == "nvme"
            assert s.device == "/dev/nvme0n1"
            assert s.mount == Path("/mnt/nvme")


# ---------------------------------------------------------------------------
# GpuInfo
# ---------------------------------------------------------------------------


class TestGpuInfo:
    def test_nvidia_model_string(self):
        gpu = GpuInfo(type="nvidia", has_cuda=True, cuda_version="12.6")
        assert gpu.model == "NVIDIA (CUDA 12.6)"

    def test_nvidia_no_version(self):
        gpu = GpuInfo(type="nvidia", has_cuda=True, cuda_version="")
        assert gpu.model == "NVIDIA"

    def test_none_model(self):
        gpu = GpuInfo(type="none", has_cuda=False, cuda_version="")
        assert gpu.model == ""


# ---------------------------------------------------------------------------
# StorageInfo
# ---------------------------------------------------------------------------


class TestStorageInfo:
    def test_nvme_is_external(self):
        s = StorageInfo(type="nvme", mount=Path("/mnt/data"), device="/dev/nvme0n1")
        assert s.is_external is True

    def test_usb_ssd_is_external(self):
        s = StorageInfo(type="usb_ssd", mount=Path("/mnt/data"), device="/dev/sda")
        assert s.is_external is True

    def test_sd_only_not_external(self):
        s = StorageInfo(type="sd_only", mount=Path.home(), device="")
        assert s.is_external is False


# ---------------------------------------------------------------------------
# Platform
# ---------------------------------------------------------------------------


class TestPlatform:
    """Platform dataclass properties: identity flags, project_root, display_name."""

    @pytest.mark.parametrize(
        "name,model,arch,storage_mount,is_jetson,is_rpi,display_name",
        [
            pytest.param(
                "jetson",
                "NVIDIA Jetson Orin Nano Super",
                "aarch64",
                "/mnt/nvme",
                True,
                False,
                "Jetson Orin Nano Super",
                id="jetson",
            ),
            pytest.param(
                "raspberry_pi",
                "Raspberry Pi 5 Model B Rev 1.0",
                "aarch64",
                "/mnt/data",
                False,
                True,
                "Raspberry Pi 5 Model B Rev 1.0",
                id="rpi5",
            ),
            pytest.param(
                "generic",
                "my-server",
                "x86_64",
                "/home/user",
                False,
                False,
                "my-server",
                id="generic",
            ),
        ],
    )
    def test_platform_properties(self, name, model, arch, storage_mount, is_jetson, is_rpi, display_name):
        """Each platform type has correct identity flags and derived properties."""
        p = make_platform(name=name, model=model, arch=arch, storage_mount=Path(storage_mount))
        assert p.is_jetson is is_jetson
        assert p.is_raspberry_pi is is_rpi
        assert p.project_root == Path(storage_mount) / "projects"
        assert p.display_name == display_name


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


class TestSingleton:
    """get_platform() singleton: caches on first call, clears on reset."""

    def test_get_platform_caches(self):
        """Second call returns the same object without re-detecting."""
        with patch("arasul_tui.core.platform.detect") as mock_detect:
            mock_detect.return_value = make_platform(has_docker=False)
            p1 = get_platform()
            p2 = get_platform()
            assert p1 is p2
            mock_detect.assert_called_once()

    def test_reset_clears_cache(self):
        """reset_platform() forces re-detection on next call."""
        with patch("arasul_tui.core.platform.detect") as mock_detect:
            mock_detect.return_value = make_platform(has_docker=False)
            get_platform()
            reset_platform()
            get_platform()
            assert mock_detect.call_count == 2


# ---------------------------------------------------------------------------
# Full detect() integration
# ---------------------------------------------------------------------------


class TestDetectIntegration:
    def test_detect_returns_platform(self):
        """detect() should return a valid Platform on any system."""
        p = detect()
        assert isinstance(p, Platform)
        assert p.name in ("jetson", "raspberry_pi", "generic")
        assert p.arch in ("aarch64", "arm64", "x86_64", "armv7l", "i686")
        assert p.ram_mb > 0

    def test_detect_on_macos_is_generic(self):
        """On macOS dev machine, platform should be 'generic'."""
        import sys

        if sys.platform == "darwin":
            p = detect()
            assert p.name == "generic"
