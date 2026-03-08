"""Extended tests for commands/system.py — status, health, setup, docker."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from arasul_tui.commands.system import (
    _setup_run_step,
    cmd_docker,
    cmd_health,
    cmd_setup,
    cmd_status,
)
from arasul_tui.core.router import REGISTRY
from arasul_tui.core.state import TuiState


@pytest.fixture
def state(tmp_path: Path) -> TuiState:
    s = TuiState(registry=REGISTRY)
    s.project_root = tmp_path
    return s


# ---------------------------------------------------------------------------
# cmd_status
# ---------------------------------------------------------------------------


class TestCmdStatus:
    def test_no_psutil(self, state: TuiState):
        with patch("arasul_tui.commands.system.psutil", None):
            result = cmd_status(state, [])
        assert result.ok is False

    def test_with_active_project(self, state: TuiState):
        state.active_project = state.project_root / "my-proj"
        state.active_project.mkdir()
        with patch("arasul_tui.commands.system.run_cmd", return_value=""):
            result = cmd_status(state, [])
        assert result.ok is True
        assert result.refresh is True

    def test_jetson_platform(self, state: TuiState):
        mock_plat = MagicMock()
        mock_plat.is_jetson = True
        mock_plat.is_raspberry_pi = False
        mock_plat.storage.mount = Path("/tmp/storage")
        mock_plat.storage.type = "nvme"
        with (
            patch("arasul_tui.commands.system.run_cmd", return_value="50"),
            patch("arasul_tui.core.platform.get_platform", return_value=mock_plat),
            patch("arasul_tui.commands.system.docker_running_count", return_value=2),
        ):
            result = cmd_status(state, [])
        assert result.ok is True

    def test_raspberry_pi_platform(self, state: TuiState):
        mock_plat = MagicMock()
        mock_plat.is_jetson = False
        mock_plat.is_raspberry_pi = True
        mock_plat.storage.mount = Path("/tmp/storage")
        mock_plat.storage.type = "usb-ssd"
        with (
            patch("arasul_tui.commands.system.run_cmd", return_value="1500"),
            patch("arasul_tui.core.platform.get_platform", return_value=mock_plat),
            patch("arasul_tui.commands.system.docker_running_count", return_value=0),
        ):
            result = cmd_status(state, [])
        assert result.ok is True

    def test_ip_fallback(self, state: TuiState):
        """When primary IP lookup fails, should fall back to hostname -I."""
        call_count = 0

        def _mock_cmd(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            if "ip -4 addr" in cmd:
                return "Error: no such device"
            if "hostname -I" in cmd:
                return "10.0.0.5"
            return ""

        with patch("arasul_tui.commands.system.run_cmd", side_effect=_mock_cmd):
            result = cmd_status(state, [])
        assert result.ok is True


# ---------------------------------------------------------------------------
# cmd_health
# ---------------------------------------------------------------------------


class TestCmdHealth:
    def test_no_psutil(self, state: TuiState):
        with patch("arasul_tui.commands.system.psutil", None):
            result = cmd_health(state, [])
        assert result.ok is False

    def test_nvme_health(self, state: TuiState):
        mock_plat = MagicMock()
        mock_plat.storage.type = "nvme"
        mock_plat.storage.device = "/dev/nvme0n1"
        mock_plat.storage.mount = Path("/tmp/storage")
        mock_plat.storage.is_external = True
        with (
            patch("arasul_tui.commands.system.run_cmd", return_value="Percentage Used: 5%"),
            patch("arasul_tui.core.platform.get_platform", return_value=mock_plat),
            patch("arasul_tui.commands.system.docker_running_count", return_value=0),
        ):
            result = cmd_health(state, [])
        assert result.ok is True

    def test_external_storage(self, state: TuiState, tmp_path: Path):
        mock_plat = MagicMock()
        mock_plat.storage.type = "usb-ssd"
        mock_plat.storage.device = "/dev/sda1"
        mock_plat.storage.mount = tmp_path
        mock_plat.storage.is_external = True
        with (
            patch("arasul_tui.commands.system.run_cmd", return_value=""),
            patch("arasul_tui.core.platform.get_platform", return_value=mock_plat),
            patch("arasul_tui.commands.system.docker_running_count", return_value=0),
        ):
            result = cmd_health(state, [])
        assert result.ok is True

    def test_fail2ban_banned(self, state: TuiState):
        def _mock_cmd(cmd, **kwargs):
            if "fail2ban-client" in cmd:
                return "Currently banned: 3"
            return ""

        with (
            patch("arasul_tui.commands.system.run_cmd", side_effect=_mock_cmd),
            patch("arasul_tui.commands.system.docker_running_count", return_value=0),
        ):
            result = cmd_health(state, [])
        assert result.ok is True

    def test_uptime_days(self, state: TuiState):
        """Uptime > 24h should show days."""
        import time

        with (
            patch("arasul_tui.commands.system.run_cmd", return_value=""),
            patch("arasul_tui.commands.system.docker_running_count", return_value=0),
            patch("arasul_tui.commands.system.psutil") as mock_psutil,
        ):
            mock_psutil.getloadavg.return_value = (0.1, 0.2, 0.3)
            vm = MagicMock()
            vm.percent = 50.0
            vm.used = 2 * 1024 * 1024 * 1024
            vm.total = 4 * 1024 * 1024 * 1024
            mock_psutil.virtual_memory.return_value = vm
            swap = MagicMock()
            swap.percent = 0.0
            swap.used = 0
            swap.total = 2 * 1024 * 1024 * 1024
            mock_psutil.swap_memory.return_value = swap
            disk = MagicMock()
            disk.percent = 30.0
            disk.used = 10 * 1024**3
            disk.total = 100 * 1024**3
            mock_psutil.disk_usage.return_value = disk
            # Boot 2 days ago
            mock_psutil.boot_time.return_value = time.time() - 2 * 86400

            result = cmd_health(state, [])
        assert result.ok is True


# ---------------------------------------------------------------------------
# cmd_setup
# ---------------------------------------------------------------------------


class TestCmdSetup:
    def test_shows_steps(self, state: TuiState):
        with patch("arasul_tui.commands.system.check_setup_status") as mock_check:
            mock_step = MagicMock()
            mock_step.name = "Network"
            mock_step.number = 2
            mock_step.description = "Configure network"
            mock_check.return_value = [(mock_step, True)]
            result = cmd_setup(state, [])
        assert result.ok is True
        assert result.pending_handler is not None

    def test_setup_run_step_invalid(self, state: TuiState):
        result = _setup_run_step(state, "abc")
        assert result.ok is False

    def test_setup_run_step_out_of_range(self, state: TuiState):
        with patch("arasul_tui.commands.system.check_setup_status") as mock_check:
            mock_check.return_value = [(MagicMock(), False)]
            result = _setup_run_step(state, "99")
        assert result.ok is False

    def test_setup_run_step_valid(self, state: TuiState):
        mock_step = MagicMock()
        mock_step.name = "Docker"
        mock_step.number = 5
        with (
            patch("arasul_tui.commands.system.check_setup_status") as mock_check,
            patch("arasul_tui.commands.system.run_setup_step", return_value=(True, "")),
            patch("arasul_tui.commands.system.spinner_run", return_value=(True, "")),
        ):
            mock_check.return_value = [(mock_step, False)]
            result = _setup_run_step(state, "1")
        assert result.ok is True

    def test_setup_run_step_failure(self, state: TuiState):
        mock_step = MagicMock()
        mock_step.name = "Docker"
        mock_step.number = 5
        with (
            patch("arasul_tui.commands.system.check_setup_status") as mock_check,
            patch("arasul_tui.commands.system.spinner_run", return_value=(False, "some error")),
        ):
            mock_check.return_value = [(mock_step, False)]
            result = _setup_run_step(state, "1")
        assert result.ok is True  # still ok, just shows warning

    def test_setup_run_all_pending(self, state: TuiState):
        mock_step = MagicMock()
        mock_step.name = "SSH"
        mock_step.number = 3
        with (
            patch("arasul_tui.commands.system.check_setup_status") as mock_check,
            patch("arasul_tui.commands.system.spinner_run", return_value=(True, "")),
        ):
            mock_check.return_value = [(mock_step, False)]
            result = _setup_run_step(state, "all")
        assert result.ok is True

    def test_setup_run_all_complete(self, state: TuiState):
        mock_step = MagicMock()
        mock_step.name = "SSH"
        with patch("arasul_tui.commands.system.check_setup_status") as mock_check:
            mock_check.return_value = [(mock_step, True)]
            result = _setup_run_step(state, "all")
        assert result.ok is True

    def test_setup_run_step_os_error(self, state: TuiState):
        mock_step = MagicMock()
        mock_step.name = "Docker"
        mock_step.number = 5
        with (
            patch("arasul_tui.commands.system.check_setup_status") as mock_check,
            patch("arasul_tui.commands.system.spinner_run", side_effect=OSError("nope")),
        ):
            mock_check.return_value = [(mock_step, False)]
            result = _setup_run_step(state, "1")
        assert result.ok is False


# ---------------------------------------------------------------------------
# cmd_docker
# ---------------------------------------------------------------------------


class TestCmdDocker:
    def test_no_containers(self, state: TuiState):
        with patch("arasul_tui.commands.system.list_containers", return_value=[]):
            result = cmd_docker(state, [])
        assert result.ok is True

    def test_with_running_containers(self, state: TuiState):
        c1 = MagicMock()
        c1.name = "n8n"
        c1.image = "n8nio/n8n:latest"
        c1.status = "Up 2 hours"
        c2 = MagicMock()
        c2.name = "postgres"
        c2.image = "postgres:16"
        c2.status = "Exited (0)"
        with patch("arasul_tui.commands.system.list_containers", return_value=[c1, c2]):
            result = cmd_docker(state, [])
        assert result.ok is True

    def test_with_long_container_names(self, state: TuiState):
        c = MagicMock()
        c.name = "a" * 50
        c.image = "b" * 100
        c.status = "Up 1 second"
        with patch("arasul_tui.commands.system.list_containers", return_value=[c]):
            result = cmd_docker(state, [])
        assert result.ok is True
