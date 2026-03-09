from __future__ import annotations

from unittest.mock import patch

from arasul_tui.core.shell import run_cmd


def test_run_cmd_echo():
    result = run_cmd("echo hello")
    assert result == "hello"


def test_run_cmd_stderr():
    result = run_cmd("echo err >&2")
    assert "err" in result


def test_run_cmd_timeout():
    result = run_cmd("sleep 10", timeout=1)
    assert "timed out" in result.lower()


def test_run_cmd_nonexistent():
    result = run_cmd("nonexistent_command_xyz 2>&1")
    # stderr merged into stdout via 2>&1, so stdout has content — returned as-is
    assert isinstance(result, str)
    assert result  # non-empty (contains shell error message)


def test_run_cmd_empty_output():
    result = run_cmd("true")
    assert result == ""


def test_run_cmd_strips_whitespace():
    result = run_cmd("echo '  padded  '")
    assert result == "padded"


def test_run_cmd_exit_code_nonzero():
    result = run_cmd("exit 1")
    # exit 1 produces no stdout/stderr — returns error indicator
    assert result.startswith("Error:")


def test_run_cmd_failed_with_stderr_gets_error_prefix():
    """Commands that fail and produce only stderr get 'Error: ' prefix."""
    result = run_cmd("ls /nonexistent_path_xyz_99")
    assert result.startswith("Error:")
    assert "nonexistent" in result.lower() or "no such" in result.lower()


def test_run_cmd_failed_with_stdout_no_prefix():
    """Commands that fail but have stdout return stdout without prefix."""
    # git diff --stat on a non-repo exits non-zero but has stderr via 2>&1
    result = run_cmd("echo 'some output' && exit 1")
    assert result == "some output"
    assert not result.startswith("Error:")


def test_run_cmd_oserror():
    """OSError during subprocess.run returns Error: prefix."""
    with patch("arasul_tui.core.shell.subprocess.run", side_effect=OSError("exec failed")):
        result = run_cmd("anything")
        assert result.startswith("Error:")
        assert "exec failed" in result
