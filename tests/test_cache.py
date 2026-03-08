from __future__ import annotations

import time
from unittest.mock import patch

from arasul_tui.core.cache import ShellCache, cached_cmd, invalidate_all, parallel_cmds


def test_cache_set_get():
    c = ShellCache(default_ttl=10)
    c.set("key", "value")
    assert c.get("key") == "value"


def test_cache_expiry():
    c = ShellCache(default_ttl=0.05)
    c.set("key", "value")
    assert c.get("key") == "value"
    time.sleep(0.1)
    assert c.get("key") is None


def test_cache_invalidate():
    c = ShellCache(default_ttl=10)
    c.set("key", "value")
    c.invalidate("key")
    assert c.get("key") is None


def test_cache_clear():
    c = ShellCache(default_ttl=10)
    c.set("a", "1")
    c.set("b", "2")
    c.clear()
    assert c.get("a") is None
    assert c.get("b") is None


def test_cached_cmd_caches():
    with patch("arasul_tui.core.shell.run_cmd", return_value="hello") as mock:
        r1 = cached_cmd("echo hello", ttl=10)
        r2 = cached_cmd("echo hello", ttl=10)
        assert r1 == "hello"
        assert r2 == "hello"
        assert mock.call_count == 1
    invalidate_all()


def test_parallel_cmds():
    with patch("arasul_tui.core.shell.run_cmd", side_effect=lambda cmd, timeout=4: cmd):
        results = parallel_cmds(
            {
                "a": ("cmd_a", 4),
                "b": ("cmd_b", 4),
            }
        )
        assert results["a"] == "cmd_a"
        assert results["b"] == "cmd_b"
    invalidate_all()


def test_invalidate_all():
    with patch("arasul_tui.core.shell.run_cmd", return_value="x"):
        cached_cmd("test_cmd", ttl=10)
    invalidate_all()
    with patch("arasul_tui.core.shell.run_cmd", return_value="y") as mock:
        r = cached_cmd("test_cmd", ttl=10)
        assert r == "y"
        assert mock.call_count == 1
    invalidate_all()
