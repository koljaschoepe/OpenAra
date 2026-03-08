"""Tests for n8n cached status and access info."""

from __future__ import annotations

import json
from unittest.mock import patch

from arasul_tui.core.n8n_client import (
    N8nAccessInfo,
    _tailscale_hostname_cached,
    n8n_access_info,
    n8n_running_cached,
)


def test_n8n_running_cached_true():
    with patch("arasul_tui.core.cache.cached_cmd", return_value="n8n-n8n-1"):
        assert n8n_running_cached() is True


def test_n8n_running_cached_false():
    with patch("arasul_tui.core.cache.cached_cmd", return_value=""):
        assert n8n_running_cached() is False


def test_n8n_running_cached_error():
    with patch("arasul_tui.core.cache.cached_cmd", return_value="Error: docker not found"):
        assert n8n_running_cached() is False


def test_tailscale_hostname_cached_valid():
    ts_json = json.dumps({"Self": {"DNSName": "mydevice.tail1234.ts.net."}})
    with patch("arasul_tui.core.cache.cached_cmd", return_value=ts_json):
        assert _tailscale_hostname_cached() == "mydevice.tail1234.ts.net"


def test_tailscale_hostname_cached_no_dot():
    ts_json = json.dumps({"Self": {"DNSName": "mydevice.ts.net"}})
    with patch("arasul_tui.core.cache.cached_cmd", return_value=ts_json):
        assert _tailscale_hostname_cached() == "mydevice.ts.net"


def test_tailscale_hostname_cached_empty():
    with patch("arasul_tui.core.cache.cached_cmd", return_value=""):
        assert _tailscale_hostname_cached() == ""


def test_tailscale_hostname_cached_invalid_json():
    with patch("arasul_tui.core.cache.cached_cmd", return_value="not json"):
        assert _tailscale_hostname_cached() == ""


def test_tailscale_hostname_cached_error():
    with patch("arasul_tui.core.cache.cached_cmd", return_value="Error: timeout"):
        assert _tailscale_hostname_cached() == ""


def test_n8n_access_info_no_tailscale():
    with (
        patch(
            "arasul_tui.core.cache.parallel_cmds",
            return_value={"n8n_running": "n8n-n8n-1", "ts_installed": ""},
        ),
        patch("arasul_tui.core.n8n_client.socket") as mock_socket,
    ):
        mock_socket.gethostname.return_value = "myjetson"
        info = n8n_access_info()

    assert isinstance(info, N8nAccessInfo)
    assert info.is_running is True
    assert info.hostname == "myjetson"
    assert info.tailscale_url == ""
    assert info.ssh_tunnel_cmd == "ssh -L 5678:localhost:5678 myjetson"
    assert info.local_url == "http://localhost:5678"


def test_n8n_access_info_with_tailscale():
    ts_json = json.dumps({"Self": {"DNSName": "myjetson.tail1234.ts.net."}})
    with (
        patch(
            "arasul_tui.core.cache.parallel_cmds",
            return_value={"n8n_running": "n8n-n8n-1", "ts_installed": "/usr/bin/tailscale"},
        ),
        patch(
            "arasul_tui.core.cache.cached_cmd",
            side_effect=lambda cmd, **kw: "tcp/5678 -> localhost:5678" if "serve" in cmd else ts_json,
        ),
        patch("arasul_tui.core.n8n_client.socket") as mock_socket,
    ):
        mock_socket.gethostname.return_value = "myjetson"
        info = n8n_access_info()

    assert info.tailscale_url == "https://myjetson.tail1234.ts.net"
    assert info.is_running is True


def test_n8n_access_info_tailscale_not_serving():
    with (
        patch(
            "arasul_tui.core.cache.parallel_cmds",
            return_value={"n8n_running": "", "ts_installed": "/usr/bin/tailscale"},
        ),
        patch("arasul_tui.core.cache.cached_cmd", return_value=""),
        patch("arasul_tui.core.n8n_client.socket") as mock_socket,
    ):
        mock_socket.gethostname.return_value = "myjetson"
        info = n8n_access_info()

    assert info.tailscale_url == ""
    assert info.is_running is False
    assert "myjetson" in info.ssh_tunnel_cmd


def test_n8n_access_info_n8n_not_running():
    with (
        patch(
            "arasul_tui.core.cache.parallel_cmds",
            return_value={"n8n_running": "", "ts_installed": ""},
        ),
        patch("arasul_tui.core.n8n_client.socket") as mock_socket,
    ):
        mock_socket.gethostname.return_value = "myjetson"
        info = n8n_access_info()

    assert info.is_running is False
