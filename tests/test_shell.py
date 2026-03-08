from __future__ import annotations

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
    # Should not raise — returns error output
    assert isinstance(result, str)


def test_run_cmd_empty_output():
    result = run_cmd("true")
    assert result == ""


def test_run_cmd_strips_whitespace():
    result = run_cmd("echo '  padded  '")
    assert result == "padded"


def test_run_cmd_exit_code_nonzero():
    result = run_cmd("exit 1")
    assert isinstance(result, str)
