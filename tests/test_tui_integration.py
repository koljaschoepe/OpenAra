"""Integration tests: verify TUI components work without Jetson hardware.

These tests ensure the TUI renders correctly on any platform (including
CI's ubuntu-latest x86) by mocking the platform as generic/RPi and
verifying that imports, state, routing, and rendering don't crash.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from arasul_tui.core.platform import (
    GpuInfo,
    Platform,
    StorageInfo,
    reset_platform,
)
from arasul_tui.core.router import REGISTRY
from arasul_tui.core.state import Screen, TuiState

# ---------------------------------------------------------------------------
# Platform fixtures
# ---------------------------------------------------------------------------

_GENERIC = Platform(
    name="generic",
    model="ci-runner",
    arch="x86_64",
    ram_mb=16384,
    gpu=GpuInfo(type="none", has_cuda=False, cuda_version=""),
    storage=StorageInfo(type="sd_only", mount=Path("/home/runner"), device=""),
    has_docker=True,
    has_nvidia_runtime=False,
)

_RPI5 = Platform(
    name="raspberry_pi",
    model="Raspberry Pi 5 Model B Rev 1.0",
    arch="aarch64",
    ram_mb=8192,
    gpu=GpuInfo(type="none", has_cuda=False, cuda_version=""),
    storage=StorageInfo(type="usb_ssd", mount=Path("/mnt/data"), device="/dev/sda"),
    has_docker=True,
    has_nvidia_runtime=False,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_platform()
    yield
    reset_platform()


def _mock_platform(p: Platform):
    return patch("arasul_tui.core.platform.get_platform", return_value=p)


# ---------------------------------------------------------------------------
# Module imports work on any platform
# ---------------------------------------------------------------------------


class TestImports:
    def test_import_app(self):
        import arasul_tui.app  # noqa: F401

    def test_import_all_commands(self):
        import arasul_tui.commands  # noqa: F401

    def test_import_platform(self):
        from arasul_tui.core.platform import detect, get_platform  # noqa: F401

    def test_import_ui(self):
        from arasul_tui.core.ui import (  # noqa: F401
            build_prompt,
            console,
            content_pad,
            print_error,
            print_header,
            print_info,
            print_result,
            print_warning,
            project_list,
        )


# ---------------------------------------------------------------------------
# State initialization on any platform
# ---------------------------------------------------------------------------


class TestStateOnAnyPlatform:
    def test_state_default(self):
        s = TuiState()
        assert s.screen == Screen.MAIN
        assert s.active_project is None

    def test_state_with_registry(self):
        s = TuiState(registry=REGISTRY)
        assert s.registry is REGISTRY

    def test_state_project_root_generic(self, tmp_path):
        s = TuiState()
        s.project_root = tmp_path
        assert s.project_root == tmp_path


# ---------------------------------------------------------------------------
# Command routing works on generic platform
# ---------------------------------------------------------------------------


class TestRoutingOnGeneric:
    def test_registry_has_commands(self):
        specs = list(REGISTRY.specs())
        assert len(specs) > 10  # should have 20+ commands

    def test_all_commands_have_handlers(self):
        for spec in REGISTRY.specs():
            assert callable(spec.handler)

    def test_help_command_on_generic(self, state):
        from arasul_tui.commands.meta import cmd_help

        with _mock_platform(_GENERIC):
            result = cmd_help(state, [])
        assert result.ok is True

    def test_status_command_on_generic(self, state):
        from arasul_tui.commands.system import cmd_status

        with (
            _mock_platform(_GENERIC),
            patch("arasul_tui.commands.system.run_cmd", return_value=""),
        ):
            result = cmd_status(state, [])
        assert result.ok is True


# ---------------------------------------------------------------------------
# Commands that check GPU gracefully degrade
# ---------------------------------------------------------------------------


class TestGpuDegradation:
    def test_create_gpu_template_fails_on_generic(self, state):
        """python-gpu template should fail on non-Jetson platform."""
        from arasul_tui.commands.project import cmd_create

        with (
            _mock_platform(_GENERIC),
            patch(
                "arasul_tui.commands.project.is_miniforge_installed",
                return_value=True,
            ),
        ):
            result = cmd_create(state, ["test-proj", "--type", "python-gpu"])
        assert result.ok is False

    def test_create_gpu_template_fails_on_rpi(self, state):
        """python-gpu template should fail on RPi (no CUDA)."""
        from arasul_tui.commands.project import cmd_create

        with (
            _mock_platform(_RPI5),
            patch(
                "arasul_tui.commands.project.is_miniforge_installed",
                return_value=True,
            ),
        ):
            result = cmd_create(state, ["test-proj", "--type", "python-gpu"])
        assert result.ok is False

    def test_create_api_template_fails_on_generic(self, state):
        """api template requires CUDA, should fail on generic Linux."""
        from arasul_tui.commands.project import cmd_create

        with (
            _mock_platform(_GENERIC),
            patch(
                "arasul_tui.commands.project.is_miniforge_installed",
                return_value=True,
            ),
        ):
            result = cmd_create(state, ["api-proj", "--type", "api"])
        assert result.ok is False

    def test_create_api_template_fails_on_rpi(self, state):
        """api template requires CUDA, should fail on RPi."""
        from arasul_tui.commands.project import cmd_create

        with (
            _mock_platform(_RPI5),
            patch(
                "arasul_tui.commands.project.is_miniforge_installed",
                return_value=True,
            ),
        ):
            result = cmd_create(state, ["api-proj", "--type", "api"])
        assert result.ok is False


# ---------------------------------------------------------------------------
# Platform display properties
# ---------------------------------------------------------------------------


class TestPlatformDisplay:
    def test_generic_display_name(self):
        assert _GENERIC.display_name == "ci-runner"

    def test_rpi_display_name(self):
        assert _RPI5.display_name == "Raspberry Pi 5 Model B Rev 1.0"

    def test_generic_project_root(self):
        assert _GENERIC.project_root == Path("/home/runner/projects")

    def test_rpi_project_root(self):
        assert _RPI5.project_root == Path("/mnt/data/projects")


# ---------------------------------------------------------------------------
# Backward compat: old .env variables still work
# ---------------------------------------------------------------------------


class TestBackwardCompat:
    def test_nvme_mount_env_still_works(self):
        """Old NVME_MOUNT env var should still be respected."""
        from arasul_tui.core.platform import detect_storage

        with patch.dict("os.environ", {"NVME_MOUNT": "/mnt/nvme"}, clear=True):
            s = detect_storage()
        assert s.mount == Path("/mnt/nvme")

    def test_storage_mount_overrides_nvme_mount(self):
        """New STORAGE_MOUNT should take precedence over old NVME_MOUNT."""
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
