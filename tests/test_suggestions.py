from __future__ import annotations

from arasul_tui.app import _suggest_alternatives


def test_suggest_close_match():
    """Should not crash and should print something for close matches."""
    # Just ensure no exceptions — output goes to mocked console
    _suggest_alternatives("statu")


def test_suggest_no_match():
    """Should not crash for totally unknown input."""
    _suggest_alternatives("xyzxyz")


def test_suggest_partial():
    """Should not crash for partial alias match."""
    _suggest_alternatives("dock")


def test_suggest_single_char():
    """Should not crash for single char."""
    _suggest_alternatives("x")
