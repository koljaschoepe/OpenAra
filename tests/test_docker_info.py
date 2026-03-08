from __future__ import annotations

from unittest.mock import patch

from arasul_tui.core.docker_info import Container, docker_running_count, list_containers


def test_container_dataclass():
    c = Container(id="abc123", name="myapp", image="nginx:latest", status="Up 2 hours", ports="80/tcp")
    assert c.name == "myapp"
    assert c.image == "nginx:latest"


def test_list_containers_empty():
    with patch("arasul_tui.core.docker_info.run_cmd", return_value=""):
        result = list_containers()
    assert result == []


def test_list_containers_with_output():
    mock_output = "abc123|myapp|nginx:latest|Up 2 hours|80/tcp"
    with patch("arasul_tui.core.docker_info.run_cmd", return_value=mock_output):
        result = list_containers()
    assert len(result) == 1
    assert result[0].name == "myapp"
    assert result[0].image == "nginx:latest"


def test_docker_running_count_zero():
    with patch("arasul_tui.core.docker_info.run_cmd", return_value="0"):
        result = docker_running_count()
    assert result == 0


def test_docker_running_count_with_containers():
    with patch("arasul_tui.core.docker_info.run_cmd", return_value="3"):
        result = docker_running_count()
    assert result == 3


def test_docker_running_count_error():
    with patch("arasul_tui.core.docker_info.run_cmd", return_value="Error: docker not found"):
        result = docker_running_count()
    assert result == 0
