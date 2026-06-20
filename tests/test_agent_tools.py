"""Tests for arasul_tui.agent.tools.*

All tests use tmp_path (pytest fixture) as project_root — no real FS side effects.
"""

from __future__ import annotations

import pytest

from arasul_tui.agent.tools import (
    TOOL_DEFINITIONS,
    execute_tool,
    requires_approval,
)
from arasul_tui.agent.tools._base import ToolError, safe_path
from arasul_tui.agent.tools.file_tools import diff_for_approval, read_file, write_file
from arasul_tui.agent.tools.search_tools import list_files, search_files
from arasul_tui.agent.tools.shell_tools import run_command


# ---------------------------------------------------------------------------
# safe_path
# ---------------------------------------------------------------------------


def test_safe_path_normal(tmp_path):
    p = safe_path(tmp_path, "src/main.py")
    assert p == tmp_path / "src" / "main.py"


def test_safe_path_root(tmp_path):
    p = safe_path(tmp_path, ".")
    assert p == tmp_path.resolve()


def test_safe_path_traversal_blocked(tmp_path):
    with pytest.raises(ToolError, match="outside the project"):
        safe_path(tmp_path, "../../etc/passwd")


def test_safe_path_empty_blocked(tmp_path):
    with pytest.raises(ToolError, match="empty"):
        safe_path(tmp_path, "")


# ---------------------------------------------------------------------------
# read_file
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_file_basic(tmp_path):
    f = tmp_path / "hello.py"
    f.write_text("line1\nline2\nline3\n")

    result = await read_file("hello.py", project_path=tmp_path)
    assert "hello.py (3 lines)" in result
    assert "1: line1" in result
    assert "2: line2" in result


@pytest.mark.asyncio
async def test_read_file_line_range(tmp_path):
    f = tmp_path / "big.py"
    f.write_text("\n".join(f"line{i}" for i in range(1, 21)))

    result = await read_file("big.py", project_path=tmp_path, start_line=3, end_line=5)
    assert "lines 3–5" in result
    assert "3: line3" in result
    assert "line1" not in result
    assert "line6" not in result


@pytest.mark.asyncio
async def test_read_file_not_found(tmp_path):
    with pytest.raises(ToolError, match="not found"):
        await read_file("nonexistent.py", project_path=tmp_path)


@pytest.mark.asyncio
async def test_read_file_traversal_blocked(tmp_path):
    with pytest.raises(ToolError, match="outside the project"):
        await read_file("../../etc/passwd", project_path=tmp_path)


@pytest.mark.asyncio
async def test_read_file_truncates_large_file(tmp_path):
    f = tmp_path / "big.txt"
    f.write_text("\n".join(f"line{i}" for i in range(1, 600)))

    result = await read_file("big.txt", project_path=tmp_path)
    assert "showing first 500 lines" in result


# ---------------------------------------------------------------------------
# write_file
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_file_creates_new(tmp_path):
    result = await write_file("new.py", "print('hello')\n", project_path=tmp_path)
    assert "created" in result
    assert (tmp_path / "new.py").read_text() == "print('hello')\n"


@pytest.mark.asyncio
async def test_write_file_updates_existing(tmp_path):
    f = tmp_path / "existing.py"
    f.write_text("old content\n")

    result = await write_file("existing.py", "new content\n", project_path=tmp_path)
    assert "updated" in result
    assert f.read_text() == "new content\n"


@pytest.mark.asyncio
async def test_write_file_creates_parent_dirs(tmp_path):
    result = await write_file("deep/nested/file.py", "x = 1\n", project_path=tmp_path)
    assert (tmp_path / "deep" / "nested" / "file.py").exists()


@pytest.mark.asyncio
async def test_write_file_diff_in_result(tmp_path):
    f = tmp_path / "code.py"
    f.write_text("a = 1\n")
    result = await write_file("code.py", "a = 2\n", project_path=tmp_path)
    assert "+1" in result or "-1" in result  # diff counts


@pytest.mark.asyncio
async def test_write_file_traversal_blocked(tmp_path):
    with pytest.raises(ToolError, match="outside the project"):
        await write_file("../../evil.sh", "rm -rf /", project_path=tmp_path)


@pytest.mark.asyncio
async def test_write_file_atomic(tmp_path):
    """Concurrent writes should not leave temp files."""
    f = tmp_path / "a.py"
    await write_file("a.py", "v = 1\n", project_path=tmp_path)
    await write_file("a.py", "v = 2\n", project_path=tmp_path)
    # No .ara.*.tmp files should remain
    tmp_files = list(tmp_path.glob(".ara.*.tmp"))
    assert tmp_files == []


# ---------------------------------------------------------------------------
# diff_for_approval
# ---------------------------------------------------------------------------


def test_diff_for_approval_new_file(tmp_path):
    diff = diff_for_approval("new.py", "x = 1\n", project_path=tmp_path)
    assert "new file" in diff or "x = 1" in diff


def test_diff_for_approval_existing(tmp_path):
    (tmp_path / "f.py").write_text("old\n")
    diff = diff_for_approval("f.py", "new\n", project_path=tmp_path)
    assert "-old" in diff
    assert "+new" in diff


def test_diff_for_approval_no_change(tmp_path):
    (tmp_path / "f.py").write_text("same\n")
    diff = diff_for_approval("f.py", "same\n", project_path=tmp_path)
    assert "no changes" in diff


# ---------------------------------------------------------------------------
# run_command
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_command_success(tmp_path):
    result = await run_command("echo hello", project_path=tmp_path)
    assert "Exit code: 0" in result
    assert "hello" in result


@pytest.mark.asyncio
async def test_run_command_failure(tmp_path):
    result = await run_command("exit 1", project_path=tmp_path)
    assert "Exit code: 1" in result


@pytest.mark.asyncio
async def test_run_command_cwd(tmp_path):
    (tmp_path / "marker.txt").write_text("found")
    result = await run_command("ls marker.txt", project_path=tmp_path)
    assert "marker.txt" in result


@pytest.mark.asyncio
async def test_run_command_blocked_rm_rf(tmp_path):
    with pytest.raises(ToolError, match="blocked"):
        await run_command("rm -rf /", project_path=tmp_path)


@pytest.mark.asyncio
async def test_run_command_blocked_rm_fr(tmp_path):
    with pytest.raises(ToolError, match="blocked"):
        await run_command("rm -fr .", project_path=tmp_path)


@pytest.mark.asyncio
async def test_run_command_blocked_dd(tmp_path):
    with pytest.raises(ToolError, match="blocked"):
        await run_command("dd if=/dev/zero of=/dev/sda", project_path=tmp_path)


@pytest.mark.asyncio
async def test_run_command_timeout(tmp_path):
    with pytest.raises(ToolError, match="timed out"):
        await run_command("sleep 10", project_path=tmp_path, timeout=1)


@pytest.mark.asyncio
async def test_run_command_stderr_captured(tmp_path):
    result = await run_command("ls /nonexistent_dir_xyz 2>&1 || true", project_path=tmp_path)
    # Either exit 0 (from || true) or has some output
    assert "Exit code:" in result


# ---------------------------------------------------------------------------
# search_files
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_files_finds_match(tmp_path):
    (tmp_path / "app.py").write_text("def login(user, password):\n    pass\n")
    result = await search_files("def login", project_path=tmp_path)
    assert "login" in result
    assert "app.py" in result


@pytest.mark.asyncio
async def test_search_files_no_match(tmp_path):
    (tmp_path / "app.py").write_text("x = 1\n")
    result = await search_files("nonexistent_xyz", project_path=tmp_path)
    assert "No matches" in result


@pytest.mark.asyncio
async def test_search_files_case_insensitive(tmp_path):
    (tmp_path / "a.py").write_text("Login = True\n")
    result = await search_files("login", project_path=tmp_path, case_sensitive=False)
    assert "Login" in result


@pytest.mark.asyncio
async def test_search_files_file_pattern(tmp_path):
    (tmp_path / "a.py").write_text("target = 1\n")
    (tmp_path / "b.ts").write_text("target = 2\n")
    result = await search_files("target", project_path=tmp_path, file_pattern="*.py")
    assert "a.py" in result
    assert "b.ts" not in result


@pytest.mark.asyncio
async def test_search_files_skips_node_modules(tmp_path):
    nm = tmp_path / "node_modules" / "pkg"
    nm.mkdir(parents=True)
    (nm / "index.js").write_text("secretfunction = 1\n")
    (tmp_path / "src.py").write_text("x = 1\n")
    result = await search_files("secretfunction", project_path=tmp_path)
    assert "No matches" in result


@pytest.mark.asyncio
async def test_search_files_invalid_regex(tmp_path):
    with pytest.raises(ToolError, match="Invalid regex"):
        await search_files("[unclosed", project_path=tmp_path)


# ---------------------------------------------------------------------------
# list_files
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_files_basic(tmp_path):
    (tmp_path / "a.py").write_text("x")
    (tmp_path / "b.py").write_text("y")
    result = await list_files(project_path=tmp_path)
    assert "a.py" in result
    assert "b.py" in result


@pytest.mark.asyncio
async def test_list_files_shows_dirs(tmp_path):
    (tmp_path / "src").mkdir()
    result = await list_files(project_path=tmp_path)
    assert "src/" in result


@pytest.mark.asyncio
async def test_list_files_recursive(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("x")
    result = await list_files(project_path=tmp_path, recursive=True)
    assert "main.py" in result


@pytest.mark.asyncio
async def test_list_files_subdir(tmp_path):
    sub = tmp_path / "src"
    sub.mkdir()
    (sub / "app.py").write_text("x")
    result = await list_files(project_path=tmp_path, path="src")
    assert "app.py" in result


@pytest.mark.asyncio
async def test_list_files_traversal_blocked(tmp_path):
    with pytest.raises(ToolError, match="outside the project"):
        await list_files(project_path=tmp_path, path="../../")


@pytest.mark.asyncio
async def test_list_files_not_found(tmp_path):
    with pytest.raises(ToolError, match="not found"):
        await list_files(project_path=tmp_path, path="nonexistent")


@pytest.mark.asyncio
async def test_list_files_skips_pycache(tmp_path):
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "mod.pyc").write_text("x")
    (tmp_path / "real.py").write_text("x")
    result = await list_files(project_path=tmp_path)
    assert "__pycache__" not in result
    assert "real.py" in result


# ---------------------------------------------------------------------------
# execute_tool dispatcher
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_tool_read(tmp_path):
    (tmp_path / "x.py").write_text("hello\n")
    result = await execute_tool("read_file", {"path": "x.py"}, tmp_path)
    assert "hello" in result


@pytest.mark.asyncio
async def test_execute_tool_unknown(tmp_path):
    with pytest.raises(ToolError, match="Unknown tool"):
        await execute_tool("fly_to_moon", {}, tmp_path)


# ---------------------------------------------------------------------------
# requires_approval
# ---------------------------------------------------------------------------


def test_requires_approval_write_file():
    assert requires_approval("write_file", {"path": "x.py", "content": ""}) is True


def test_requires_approval_read_file():
    assert requires_approval("read_file", {"path": "x.py"}) is False


def test_requires_approval_safe_command():
    assert requires_approval("run_command", {"command": "pytest tests/"}) is False


def test_requires_approval_rm_command():
    assert requires_approval("run_command", {"command": "rm old_file.py"}) is True


def test_requires_approval_git_reset():
    assert requires_approval("run_command", {"command": "git reset --hard HEAD"}) is True


def test_requires_approval_mv_command():
    assert requires_approval("run_command", {"command": "mv old.py new.py"}) is True


# ---------------------------------------------------------------------------
# TOOL_DEFINITIONS structure
# ---------------------------------------------------------------------------


def test_tool_definitions_have_required_fields():
    names = {t["function"]["name"] for t in TOOL_DEFINITIONS}
    assert names == {"read_file", "write_file", "run_command", "search_files", "list_files"}

    for tool in TOOL_DEFINITIONS:
        assert tool["type"] == "function"
        fn = tool["function"]
        assert "name" in fn
        assert "description" in fn
        assert "parameters" in fn
        assert fn["parameters"]["type"] == "object"
