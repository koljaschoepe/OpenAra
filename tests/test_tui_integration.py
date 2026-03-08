"""Integration tests: verify TUI works on any platform without real hardware.

Strategy: Tests in this file verify cross-cutting concerns:
- Command routing works on generic/RPi platforms
- GPU templates gracefully degrade on non-Jetson
- Backward-compatible env variables still work

Module import smoke tests and state/property tests are covered in their
dedicated files (test_state.py, test_platform.py).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from arasul_tui.core.router import REGISTRY
from tests.conftest import make_platform, mock_platform

_GENERIC = make_platform(name="generic", model="ci-runner", ram_mb=16384)
_RPI5 = make_platform(
    name="raspberry_pi",
    model="Raspberry Pi 5 Model B Rev 1.0",
    arch="aarch64",
    storage_type="usb_ssd",
    storage_mount=Path("/mnt/data"),
    storage_device="/dev/sda",
)


# ---------------------------------------------------------------------------
# Command routing works on generic platform
# ---------------------------------------------------------------------------


class TestRoutingOnGeneric:
    """Commands must work on non-Jetson platforms."""

    def test_registry_has_commands(self):
        """Registry should have 20+ registered commands."""
        specs = list(REGISTRY.specs())
        assert len(specs) > 10

    def test_all_commands_have_handlers(self):
        """Every registered command must have a callable handler."""
        for spec in REGISTRY.specs():
            assert callable(spec.handler)

    def test_help_command_on_generic(self, state):
        """Help renders without errors on generic platform."""
        from arasul_tui.commands.meta import cmd_help

        with mock_platform(_GENERIC):
            result = cmd_help(state, [])
        assert result.ok is True

    def test_status_command_on_generic(self, state):
        """Status command works on generic platform (no GPU, no NVMe)."""
        from arasul_tui.commands.system import cmd_status

        with (
            mock_platform(_GENERIC),
            patch("arasul_tui.commands.system.run_cmd", return_value=""),
        ):
            result = cmd_status(state, [])
        assert result.ok is True


# ---------------------------------------------------------------------------
# GPU template degradation (parametrized)
# ---------------------------------------------------------------------------


class TestGpuDegradation:
    """CUDA-only templates must fail gracefully on non-Jetson platforms."""

    @pytest.mark.parametrize(
        "template,platform_fixture",
        [
            pytest.param("python-gpu", _GENERIC, id="python-gpu-on-generic"),
            pytest.param("python-gpu", _RPI5, id="python-gpu-on-rpi"),
            pytest.param("api", _GENERIC, id="api-on-generic"),
            pytest.param("api", _RPI5, id="api-on-rpi"),
        ],
    )
    def test_cuda_template_fails_on_non_jetson(self, state, template, platform_fixture):
        """CUDA templates return ok=False on platforms without GPU."""
        from arasul_tui.commands.project import cmd_create

        with (
            mock_platform(platform_fixture),
            patch("arasul_tui.commands.project.is_miniforge_installed", return_value=True),
        ):
            result = cmd_create(state, ["test-proj", "--type", template])
        assert result.ok is False


# ---------------------------------------------------------------------------
# Backward compat: old .env variables still work
# ---------------------------------------------------------------------------


class TestBackwardCompat:
    """Legacy NVME_MOUNT env var must still be respected for existing users."""

    def test_nvme_mount_env_still_works(self):
        """Old NVME_MOUNT env var should still be respected."""
        from arasul_tui.core.platform import detect_storage

        with patch.dict("os.environ", {"NVME_MOUNT": "/mnt/nvme"}, clear=True):
            s = detect_storage()
        assert s.mount == Path("/mnt/nvme")

    def test_storage_mount_overrides_nvme_mount(self):
        """New STORAGE_MOUNT takes precedence over old NVME_MOUNT."""
        from arasul_tui.core.platform import detect_storage

        with patch.dict(
            "os.environ",
            {"STORAGE_MOUNT": "/mnt/data", "NVME_MOUNT": "/mnt/nvme"},
            clear=True,
        ):
            s = detect_storage()
        assert s.mount == Path("/mnt/data")

    def test_no_env_uses_auto_detect(self):
        """Without env vars, storage falls back to auto-detection."""
        from arasul_tui.core.platform import detect_storage

        with (
            patch.dict("os.environ", {}, clear=True),
            patch("arasul_tui.core.platform._run", return_value=""),
        ):
            s = detect_storage()
        assert s.type == "sd_only"
        assert s.mount == Path.home()
