"""RPi compatibility tests — verify platform-conditional paths unique to Raspberry Pi.

Strategy: Platform property tests and detection logic are covered in test_platform.py.
This file only tests RPi-specific behaviors NOT tested elsewhere:
- Template filtering (CUDA exclusion)
- Dashboard vcgencmd integration
- Shell config file existence
- Browser cache on external storage
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from tests.conftest import make_platform, mock_platform


def _rpi4(tmp_path: Path):
    return make_platform(
        name="raspberry_pi",
        model="Raspberry Pi 4 Model B Rev 1.5",
        arch="aarch64",
        ram_mb=4096,
        storage_type="usb_ssd",
        storage_mount=tmp_path / "data",
        storage_device="/dev/sda",
    )


def _rpi5(tmp_path: Path):
    return make_platform(
        name="raspberry_pi",
        model="Raspberry Pi 5 Model B Rev 1.0",
        arch="aarch64",
        storage_type="nvme",
        storage_mount=tmp_path / "nvme",
        storage_device="/dev/nvme0n1",
    )


# ---------------------------------------------------------------------------
# GPU template filtering (RPi must NOT see CUDA templates)
# ---------------------------------------------------------------------------


class TestRPiTemplateFiltering:
    """CUDA templates must be hidden on RPi; non-CUDA templates must remain."""

    def test_no_cuda_templates_on_rpi(self, tmp_path: Path):
        p = _rpi4(tmp_path)
        with mock_platform(p):
            from arasul_tui.core.templates import list_available_templates

            available = list_available_templates()
            names = [t.name for t in available]
            assert "python-gpu" not in names
            assert "vision" not in names
            assert "api" not in names

    def test_non_cuda_templates_available(self, tmp_path: Path):
        p = _rpi5(tmp_path)
        with mock_platform(p):
            from arasul_tui.core.templates import list_available_templates

            available = list_available_templates()
            names = [t.name for t in available]
            assert "notebook" in names
            assert "webapp" in names


# ---------------------------------------------------------------------------
# Dashboard _system_info with RPi platform
# ---------------------------------------------------------------------------


class TestRPiDashboard:
    """Dashboard must use vcgencmd on RPi, and omit GPU/power rows."""

    def test_system_info_rpi_uses_vcgencmd(self, tmp_path: Path):
        p = _rpi4(tmp_path)
        with (
            mock_platform(p),
            patch("arasul_tui.core.ui.dashboard.cached_cmd", return_value=""),
            patch("arasul_tui.core.ui.dashboard.parallel_cmds") as mock_parallel,
        ):
            mock_parallel.return_value = {
                "disk": "10G/100G",
                "disk_pct": "10",
                "temp": "52",
                "ip": "192.168.1.50",
                "docker": "1",
                "freq": "1500",
                "throttle": "0x0",
            }
            from arasul_tui.core.ui.dashboard import _system_info

            _system_info()

            call_args = mock_parallel.call_args[0][0]
            assert "freq" in call_args
            assert "throttle" in call_args
            assert "vcgencmd" in call_args["temp"][0]
            assert "gpu" not in call_args
            assert "power" not in call_args

    def test_system_info_rpi5_nvme(self, tmp_path: Path):
        """RPi 5 with NVMe runs without errors."""
        p = _rpi5(tmp_path)
        (tmp_path / "nvme").mkdir(exist_ok=True)
        with (
            mock_platform(p),
            patch("arasul_tui.core.ui.dashboard.cached_cmd", return_value=""),
            patch("arasul_tui.core.ui.dashboard.parallel_cmds") as mock_parallel,
        ):
            mock_parallel.return_value = {
                "disk": "50G/1.8T",
                "disk_pct": "3",
                "temp": "45",
                "ip": "192.168.1.51",
                "docker": "0",
                "freq": "2400",
                "throttle": "0x0",
            }
            from arasul_tui.core.ui.dashboard import _system_info

            info = _system_info()
        assert info["temp"] == 45


# ---------------------------------------------------------------------------
# Shell config files (real file checks — not covered elsewhere)
# ---------------------------------------------------------------------------


class TestRPiShellScripts:
    """Config files for RPi must exist and contain expected content."""

    def test_aliases_file_exists(self):
        alias_file = Path(__file__).resolve().parent.parent / "config" / "aliases" / "raspberry_pi"
        assert alias_file.exists(), "config/aliases/raspberry_pi must exist"

    def test_aliases_has_vcgencmd(self):
        alias_file = Path(__file__).resolve().parent.parent / "config" / "aliases" / "raspberry_pi"
        content = alias_file.read_text()
        assert "vcgencmd" in content

    def test_common_aliases_exist(self):
        alias_file = Path(__file__).resolve().parent.parent / "config" / "aliases" / "common"
        assert alias_file.exists(), "config/aliases/common must exist"

    def test_motd_file_exists(self):
        motd = Path(__file__).resolve().parent.parent / "config" / "motd-arasul"
        assert motd.exists(), "config/motd-arasul must exist"

    def test_motd_has_rpi_branch(self):
        motd = Path(__file__).resolve().parent.parent / "config" / "motd-arasul"
        content = motd.read_text()
        assert "raspberry" in content.lower() or "Raspberry" in content


# ---------------------------------------------------------------------------
# Browser cache path on RPi (external storage)
# ---------------------------------------------------------------------------


class TestRPiBrowserCache:
    """Browser cache must use external storage mount, not home dir."""

    def test_browser_cache_on_external_storage(self, tmp_path: Path):
        p = _rpi4(tmp_path)
        with mock_platform(p):
            from arasul_tui.core.browser import _storage_browser_cache

            result = _storage_browser_cache()
            assert result == tmp_path / "data" / "playwright-browsers"
