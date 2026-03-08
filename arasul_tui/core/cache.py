"""Caching and parallel execution layer for shell commands."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from threading import Lock
from typing import Any


@dataclass
class _CacheEntry:
    value: Any
    expires: float


class ShellCache:
    """Thread-safe TTL cache for shell command results."""

    def __init__(self, default_ttl: float = 30.0) -> None:
        self._store: dict[str, _CacheEntry] = {}
        self._lock = Lock()
        self._default_ttl = default_ttl

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._store.get(key)
            if entry and time.monotonic() < entry.expires:
                return entry.value
            if entry:
                del self._store[key]
        return None

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        with self._lock:
            self._store[key] = _CacheEntry(
                value=value,
                expires=time.monotonic() + (ttl if ttl is not None else self._default_ttl),
            )

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


# Global cache instance
_cache = ShellCache(default_ttl=30.0)


def cached_cmd(cmd: str, timeout: int = 4, ttl: float | None = None) -> str:
    """Run a shell command with caching. Returns cached result if fresh."""
    from arasul_tui.core.shell import run_cmd

    cached = _cache.get(cmd)
    if cached is not None:
        return cached

    result = run_cmd(cmd, timeout=timeout)
    _cache.set(cmd, result, ttl=ttl)
    return result


def parallel_cmds(cmds: dict[str, tuple[str, int]]) -> dict[str, str]:
    """Run multiple shell commands in parallel.

    Args:
        cmds: Mapping of key -> (command, timeout).

    Returns:
        Mapping of key -> result string.
    """
    from arasul_tui.core.shell import run_cmd

    results: dict[str, str] = {}

    # Check cache first
    uncached: dict[str, tuple[str, int]] = {}
    for key, (cmd, timeout) in cmds.items():
        cached = _cache.get(cmd)
        if cached is not None:
            results[key] = cached
        else:
            uncached[key] = (cmd, timeout)

    if not uncached:
        return results

    with ThreadPoolExecutor(max_workers=min(4, len(uncached))) as pool:
        futures = {pool.submit(run_cmd, cmd, timeout): (key, cmd) for key, (cmd, timeout) in uncached.items()}
        for future in as_completed(futures):
            key, cmd = futures[future]
            try:
                result = future.result()
            except (OSError, TimeoutError) as exc:
                result = f"Error: {exc}"
            results[key] = result
            _cache.set(cmd, result)

    return results


def invalidate_all() -> None:
    """Clear all cached results."""
    _cache.clear()
