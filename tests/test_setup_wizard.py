from __future__ import annotations

from unittest.mock import patch

from arasul_tui.core.setup_wizard import SETUP_STEPS, SetupStep, check_setup_status


def test_setup_steps_count():
    """All 9 setup steps are defined."""
    assert len(SETUP_STEPS) == 9


def test_setup_step_numbers():
    """Steps are numbered 1-9."""
    numbers = [s.number for s in SETUP_STEPS]
    assert numbers == list(range(1, 10))


def test_setup_step_has_script():
    """Each step has a script path."""
    for step in SETUP_STEPS:
        assert step.script.startswith("scripts/")
        assert step.script.endswith(".sh")


def test_setup_step_dataclass():
    """SetupStep dataclass works correctly."""
    step = SetupStep(
        number=1,
        name="Test",
        description="A test step",
        script="scripts/test.sh",
        check_done=lambda: True,
    )
    assert step.name == "Test"
    assert step.check_done() is True


def test_check_setup_status():
    """check_setup_status returns tuples of (step, bool)."""
    with patch("arasul_tui.core.setup_wizard.run_cmd", return_value=""):
        status = check_setup_status()
    assert len(status) == 9
    for step, done in status:
        assert isinstance(step, SetupStep)
        assert isinstance(done, bool)
