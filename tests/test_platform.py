"""Tests for arasul_tui.core.platform — hardware detection layer."""

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

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset():
    """Clear platform singleton between tests."""
    reset_platform()
    yield
    reset_platform()


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
    @pytest.fixture
    def jetson(self):
        return Platform(
            name="jetson",
            model="NVIDIA Jetson Orin Nano Super",
            arch="aarch64",
            ram_mb=8192,
            gpu=GpuInfo(type="nvidia", has_cuda=True, cuda_version="12.6"),
            storage=StorageInfo(type="nvme", mount=Path("/mnt/nvme"), device="/dev/nvme0n1"),
            has_docker=True,
            has_nvidia_runtime=True,
        )

    @pytest.fixture
    def rpi5(self):
        return Platform(
            name="raspberry_pi",
            model="Raspberry Pi 5 Model B Rev 1.0",
            arch="aarch64",
            ram_mb=8192,
            gpu=GpuInfo(type="none", has_cuda=False, cuda_version=""),
            storage=StorageInfo(type="usb_ssd", mount=Path("/mnt/data"), device="/dev/sda"),
            has_docker=True,
            has_nvidia_runtime=False,
        )

    @pytest.fixture
    def generic(self):
        return Platform(
            name="generic",
            model="my-server",
            arch="x86_64",
            ram_mb=16384,
            gpu=GpuInfo(type="none", has_cuda=False, cuda_version=""),
            storage=StorageInfo(type="sd_only", mount=Path("/home/user"), device=""),
            has_docker=True,
            has_nvidia_runtime=False,
        )

    def test_jetson_properties(self, jetson):
        assert jetson.is_jetson is True
        assert jetson.is_raspberry_pi is False
        assert jetson.project_root == Path("/mnt/nvme/projects")
        assert jetson.display_name == "Jetson Orin Nano Super"

    def test_rpi_properties(self, rpi5):
        assert rpi5.is_jetson is False
        assert rpi5.is_raspberry_pi is True
        assert rpi5.project_root == Path("/mnt/data/projects")
        assert rpi5.display_name == "Raspberry Pi 5 Model B Rev 1.0"

    def test_generic_properties(self, generic):
        assert generic.is_jetson is False
        assert generic.is_raspberry_pi is False
        assert generic.project_root == Path("/home/user/projects")


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


class TestSingleton:
    def test_get_platform_caches(self):
        with patch("arasul_tui.core.platform.detect") as mock_detect:
            mock_detect.return_value = Platform(
                name="generic",
                model="test",
                arch="x86_64",
                ram_mb=4096,
                gpu=GpuInfo(type="none", has_cuda=False, cuda_version=""),
                storage=StorageInfo(type="sd_only", mount=Path("/home"), device=""),
                has_docker=False,
                has_nvidia_runtime=False,
            )
            p1 = get_platform()
            p2 = get_platform()
            assert p1 is p2
            mock_detect.assert_called_once()

    def test_reset_clears_cache(self):
        with patch("arasul_tui.core.platform.detect") as mock_detect:
            mock_detect.return_value = Platform(
                name="generic",
                model="test",
                arch="x86_64",
                ram_mb=4096,
                gpu=GpuInfo(type="none", has_cuda=False, cuda_version=""),
                storage=StorageInfo(type="sd_only", mount=Path("/home"), device=""),
                has_docker=False,
                has_nvidia_runtime=False,
            )
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
