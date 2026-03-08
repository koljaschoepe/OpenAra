"""Tests for Docker container listing and counting.

Strategy: Tests verify run_cmd output parsing (docker ps format) and
error handling (docker not available). Real docker is never called.
"""

from __future__ import annotations

from unittest.mock import patch

from arasul_tui.core.docker_info import docker_running_count, list_containers


def test_list_containers_empty():
    """Empty docker output returns empty list."""
    with patch("arasul_tui.core.docker_info.run_cmd", return_value=""):
        result = list_containers()
    assert result == []


def test_list_containers_with_output():
    """Pipe-delimited docker output is parsed into Container objects."""
    mock_output = "abc123|myapp|nginx:latest|Up 2 hours|80/tcp"
    with patch("arasul_tui.core.docker_info.run_cmd", return_value=mock_output):
        result = list_containers()
    assert len(result) == 1
    assert result[0].name == "myapp"
    assert result[0].image == "nginx:latest"


def test_docker_running_count_zero():
    """Zero containers reported when docker returns '0'."""
    with patch("arasul_tui.core.docker_info.run_cmd", return_value="0"):
        assert docker_running_count() == 0


def test_docker_running_count_with_containers():
    """Container count parsed from docker output."""
    with patch("arasul_tui.core.docker_info.run_cmd", return_value="3"):
        assert docker_running_count() == 3


def test_docker_running_count_error():
    """Returns 0 when docker command fails."""
    with patch("arasul_tui.core.docker_info.run_cmd", return_value="Error: docker not found"):
        assert docker_running_count() == 0
