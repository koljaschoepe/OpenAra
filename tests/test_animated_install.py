"""Tests for core/ui/animated_install.py — build_install_panel rendering."""

from __future__ import annotations

import pytest
from rich.padding import Padding

from arasul_tui.core.ui.animated_install import (
    build_install_panel,
)

SAMPLE_STEPS = [
    ("Download", "Fetching installer"),
    ("Install", "Running installer"),
    ("Configure", "Setting up config"),
]


class TestBuildInstallPanel:
    def test_all_pending(self):
        states = [False, False, False]
        result = build_install_panel("Test Setup", SAMPLE_STEPS, states, 0, 0, 0.0, False, False)
        assert isinstance(result, Padding)

    def test_partial_progress(self):
        states = [True, False, False]
        result = build_install_panel("Test Setup", SAMPLE_STEPS, states, 1, 5, 10.0, False, False)
        assert isinstance(result, Padding)

    def test_all_done(self):
        states = [True, True, True]
        result = build_install_panel("Test Setup", SAMPLE_STEPS, states, 2, 10, 30.0, True, False)
        assert isinstance(result, Padding)

    def test_failed_state(self):
        states = [True, False, False]
        result = build_install_panel("Test Setup", SAMPLE_STEPS, states, 1, 5, 15.0, False, True)
        assert isinstance(result, Padding)

    def test_long_elapsed_time(self):
        states = [True, True, False]
        # 2 minutes 30 seconds
        result = build_install_panel("Test Setup", SAMPLE_STEPS, states, 2, 0, 150.0, False, False)
        assert isinstance(result, Padding)

    def test_zero_steps(self):
        """Edge case: empty steps list causes ZeroDivisionError."""
        with pytest.raises(ZeroDivisionError):
            build_install_panel("Empty", [], [], 0, 0, 0.0, False, False)

    def test_single_step(self):
        result = build_install_panel(
            "Single",
            [("Only Step", "detail")],
            [False],
            0,
            0,
            0.0,
            False,
            False,
        )
        assert isinstance(result, Padding)

    def test_single_step_done(self):
        result = build_install_panel(
            "Single Done",
            [("Only Step", "detail")],
            [True],
            0,
            0,
            5.0,
            True,
            False,
        )
        assert isinstance(result, Padding)

    def test_spinner_frame_wraps(self):
        """Frame index larger than spinner frames should wrap."""
        states = [False]
        result = build_install_panel("Wrap", [("Step", "d")], states, 0, 999, 0.0, False, False)
        assert isinstance(result, Padding)

    def test_short_elapsed(self):
        """Elapsed < 60s should show seconds only."""
        states = [False, False]
        result = build_install_panel(
            "Short",
            [("A", "a"), ("B", "b")],
            states,
            0,
            0,
            42.0,
            False,
            False,
        )
        assert isinstance(result, Padding)
