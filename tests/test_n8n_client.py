from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from arasul_tui.core.n8n_client import (
    n8n_compose_cmd,
    n8n_get_api_key,
    n8n_is_installed,
    n8n_is_running,
    n8n_list_workflows,
    n8n_save_api_key,
)


def test_n8n_is_installed_false():
    with patch("arasul_tui.core.n8n_client.n8n_dir", return_value=Path("/nonexistent")):
        assert n8n_is_installed() is False


def test_n8n_is_installed_true(tmp_path: Path):
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("version: '3.8'")
    with patch("arasul_tui.core.n8n_client.n8n_dir", return_value=tmp_path):
        assert n8n_is_installed() is True


def test_n8n_is_running_false():
    with patch("arasul_tui.core.n8n_client.run_cmd", return_value=""):
        assert n8n_is_running() is False


def test_n8n_is_running_true():
    with patch("arasul_tui.core.n8n_client.run_cmd", return_value="n8n-n8n-1"):
        assert n8n_is_running() is True


def test_n8n_is_running_error():
    with patch("arasul_tui.core.n8n_client.run_cmd", return_value="Error: docker not found"):
        assert n8n_is_running() is False


def test_n8n_list_workflows_no_api_key():
    with patch("arasul_tui.core.n8n_client.n8n_get_api_key", return_value=None):
        result = n8n_list_workflows()
    assert result == []


def test_n8n_get_api_key_no_config():
    with patch("arasul_tui.core.n8n_client.N8N_CONFIG", Path("/nonexistent/n8n.yaml")):
        assert n8n_get_api_key() is None


def test_n8n_save_and_get_api_key(tmp_path: Path):
    config = tmp_path / "n8n.yaml"
    with patch("arasul_tui.core.n8n_client.N8N_CONFIG", config):
        n8n_save_api_key("test-key-12345")
        assert config.exists()
        key = n8n_get_api_key()
        assert key == "test-key-12345"


def test_n8n_save_api_key_creates_parent(tmp_path: Path):
    config = tmp_path / "subdir" / "n8n.yaml"
    with patch("arasul_tui.core.n8n_client.N8N_CONFIG", config):
        n8n_save_api_key("my-key")
        assert config.exists()


def test_n8n_compose_cmd():
    with patch("arasul_tui.core.n8n_client.run_cmd", return_value="done") as mock:
        result = n8n_compose_cmd("up -d")
    assert result == "done"
    assert "docker compose" in mock.call_args[0][0]
    assert "up -d" in mock.call_args[0][0]


def test_n8n_list_workflows_with_data():
    mock_response = {"data": [{"id": "1", "name": "Test", "active": True}]}
    with patch("arasul_tui.core.n8n_client.n8n_api_request", return_value=mock_response):
        result = n8n_list_workflows()
    assert len(result) == 1
    assert result[0]["name"] == "Test"


def test_n8n_list_workflows_empty_response():
    with patch("arasul_tui.core.n8n_client.n8n_api_request", return_value=None):
        result = n8n_list_workflows()
    assert result == []
