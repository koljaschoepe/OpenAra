from __future__ import annotations

from arasul_tui.app import _fuzzy_match


def test_exact_match():
    assert _fuzzy_match("my-app", ["my-app", "my-other"]) == ["my-app"]


def test_prefix_match():
    assert _fuzzy_match("my", ["my-app", "my-other", "utils"]) == ["my-app", "my-other"]


def test_substring_match():
    assert _fuzzy_match("app", ["my-app", "utils"]) == ["my-app"]


def test_fuzzy_chars():
    result = _fuzzy_match("mya", ["my-app", "my-other", "utils"])
    assert "my-app" in result


def test_no_match():
    assert _fuzzy_match("zzz", ["my-app", "utils"]) == []


def test_case_insensitive():
    assert _fuzzy_match("MY", ["my-app"]) == ["my-app"]


def test_empty_query():
    assert _fuzzy_match("", ["my-app", "utils"]) == ["my-app", "utils"]
