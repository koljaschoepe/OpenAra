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
from arasul_tui.agent.tools.file_tools import diff_for_approval, read_file, undo_file, write_file
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
    assert names == {"read_file", "write_file", "undo_file", "run_command", "search_files", "list_files"}

    for tool in TOOL_DEFINITIONS:
        assert tool["type"] == "function"
        fn = tool["function"]
        assert "name" in fn
        assert "description" in fn
        assert "parameters" in fn
        assert fn["parameters"]["type"] == "object"


# ---------------------------------------------------------------------------
# write_file — backup on overwrite
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_file_creates_backup_on_overwrite(tmp_path):
    """Overwriting an existing file must create a .openara-backups/ entry."""
    target = tmp_path / "auth.py"
    target.write_text("original content\n")

    await write_file("auth.py", "new content\n", tmp_path)

    backup_root = tmp_path / ".openara-backups" / "auth.py"
    backups = list(backup_root.glob("*.bak"))
    assert len(backups) == 1
    assert backups[0].read_text() == "original content\n"


@pytest.mark.asyncio
async def test_write_file_no_backup_on_create(tmp_path):
    """Creating a new file must NOT create a backup (nothing to back up)."""
    await write_file("new.py", "hello\n", tmp_path)
    assert not (tmp_path / ".openara-backups").exists()


@pytest.mark.asyncio
async def test_write_file_backup_pruned_to_max(tmp_path):
    """After 11+ overwrites, only the last 10 backups are kept."""
    target = tmp_path / "f.py"
    for i in range(12):
        target.write_text(f"version {i}\n")
        await write_file("f.py", f"version {i+1}\n", tmp_path)

    backup_dir = tmp_path / ".openara-backups" / "f.py"
    backups = list(backup_dir.glob("*.bak"))
    assert len(backups) == 10


# ---------------------------------------------------------------------------
# undo_file
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_undo_file_restores_previous_version(tmp_path):
    """undo_file restores the file to its pre-write content."""
    (tmp_path / "auth.py").write_text("original\n")
    await write_file("auth.py", "changed\n", tmp_path)

    assert (tmp_path / "auth.py").read_text() == "changed\n"
    await undo_file("auth.py", tmp_path)
    assert (tmp_path / "auth.py").read_text() == "original\n"


@pytest.mark.asyncio
async def test_undo_file_multi_step(tmp_path):
    """Calling undo_file twice steps back two versions."""
    (tmp_path / "f.py").write_text("v1\n")
    await write_file("f.py", "v2\n", tmp_path)
    await write_file("f.py", "v3\n", tmp_path)

    await undo_file("f.py", tmp_path)
    assert (tmp_path / "f.py").read_text() == "v2\n"
    await undo_file("f.py", tmp_path)
    assert (tmp_path / "f.py").read_text() == "v1\n"


@pytest.mark.asyncio
async def test_undo_file_no_backup_returns_message(tmp_path):
    """undo_file on a file with no backup returns a human-readable message."""
    (tmp_path / "fresh.py").write_text("hello\n")
    result = await undo_file("fresh.py", tmp_path)
    assert "no backup" in result.lower()


@pytest.mark.asyncio
async def test_undo_not_requires_approval(tmp_path):
    """undo_file should never require approval — it's a restoration."""
    from arasul_tui.agent.tools import requires_approval
    assert not requires_approval("undo_file", {"path": "auth.py"})


# ---------------------------------------------------------------------------
# on_llm_start callback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_llm_start_fired_before_each_llm_call(tmp_path):
    """on_llm_start must be called once per LLM iteration."""
    from unittest.mock import AsyncMock, patch
    from arasul_tui.agent.agent import AgentCallbacks, AgentSession
    from arasul_tui.agent.config import AgentConfig
    from arasul_tui.agent.llm import LLMResponse, Usage

    llm_starts: list[int] = []

    cb = AgentCallbacks(on_llm_start=lambda: llm_starts.append(1))
    cfg = AgentConfig(base_url="http://localhost:11434/v1", model="qwen3:14b")

    async def mock_chat(messages, system, tools, config, on_token=None, on_tool_start=None):
        return LLMResponse(text="Done.", stop_reason="end_turn", usage=Usage(100, 50))

    with patch("arasul_tui.agent.agent.chat", AsyncMock(side_effect=mock_chat)):
        session = AgentSession(tmp_path, config=cfg, callbacks=cb)
        await session.run("First task")
        await session.run("Second task")

    assert len(llm_starts) == 2  # one per turn (each single-iteration)


@pytest.mark.asyncio
async def test_think_false_adds_no_think_to_system(tmp_path):
    """When think=False, system prompt must contain /no_think."""
    from unittest.mock import AsyncMock, patch
    from arasul_tui.agent.agent import AgentSession
    from arasul_tui.agent.config import AgentConfig
    from arasul_tui.agent.llm import LLMResponse, Usage

    captured_systems: list[str] = []

    async def mock_chat(messages, system, tools, config, on_token=None, on_tool_start=None):
        captured_systems.append(system)
        return LLMResponse(text="Done.", stop_reason="end_turn", usage=Usage(100, 50))

    cfg = AgentConfig(
        base_url="http://localhost:11434/v1",
        model="qwen3:14b",
        think=False,
    )
    with patch("arasul_tui.agent.agent.chat", AsyncMock(side_effect=mock_chat)):
        session = AgentSession(tmp_path, config=cfg)
        await session.run("Do something")

    assert captured_systems and captured_systems[0].endswith("/no_think")


# ---------------------------------------------------------------------------
# AgentSession — system_override
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_system_override_used_as_is(tmp_path):
    """system_override replaces the normal system prompt entirely."""
    from unittest.mock import AsyncMock, patch
    from arasul_tui.agent.agent import AgentSession
    from arasul_tui.agent.config import AgentConfig
    from arasul_tui.agent.llm import LLMResponse, Usage

    captured: list[str] = []

    async def mock_chat(messages, system, tools, config, on_token=None, on_tool_start=None):
        captured.append(system)
        return LLMResponse(text="Done.", stop_reason="end_turn", usage=Usage(50, 50))

    override = "You are a custom reviewer."
    cfg = AgentConfig(base_url="http://localhost:11434/v1", model="qwen3:14b")
    with patch("arasul_tui.agent.agent.chat", AsyncMock(side_effect=mock_chat)):
        session = AgentSession(tmp_path, config=cfg, system_override=override)
        await session.run("Review this")

    assert captured[0] == override  # exact match, no repo map appended


@pytest.mark.asyncio
async def test_session_system_override_respects_no_think(tmp_path):
    """system_override + think=False should append /no_think."""
    from unittest.mock import AsyncMock, patch
    from arasul_tui.agent.agent import AgentSession
    from arasul_tui.agent.config import AgentConfig
    from arasul_tui.agent.llm import LLMResponse, Usage

    captured: list[str] = []

    async def mock_chat(messages, system, tools, config, on_token=None, on_tool_start=None):
        captured.append(system)
        return LLMResponse(text="Done.", stop_reason="end_turn", usage=Usage(50, 50))

    override = "You are a reviewer."
    cfg = AgentConfig(base_url="http://localhost:11434/v1", model="qwen3:14b", think=False)
    with patch("arasul_tui.agent.agent.chat", AsyncMock(side_effect=mock_chat)):
        session = AgentSession(tmp_path, config=cfg, system_override=override)
        await session.run("Review")

    assert captured[0] == override + "\n/no_think"


@pytest.mark.asyncio
async def test_session_system_not_refreshed_when_override_set(tmp_path):
    """With system_override, the system prompt must not change between tasks."""
    from unittest.mock import AsyncMock, patch
    from arasul_tui.agent.agent import AgentSession
    from arasul_tui.agent.config import AgentConfig
    from arasul_tui.agent.llm import LLMResponse, Usage

    systems: list[str] = []

    async def mock_chat(messages, system, tools, config, on_token=None, on_tool_start=None):
        systems.append(system)
        return LLMResponse(text="Done.", stop_reason="end_turn", usage=Usage(50, 50))

    override = "Fixed system."
    cfg = AgentConfig(base_url="http://localhost:11434/v1", model="qwen3:14b")
    with patch("arasul_tui.agent.agent.chat", AsyncMock(side_effect=mock_chat)):
        session = AgentSession(tmp_path, config=cfg, system_override=override)
        await session.run("Task A")
        await session.run("Task B with a different hint")

    assert systems[0] == systems[1] == override


# ---------------------------------------------------------------------------
# _get_git_diff helper
# ---------------------------------------------------------------------------


def test_get_git_diff_non_git_dir(tmp_path):
    """Non-git directory returns (None, False)."""
    from arasul_tui.commands.agent_cmd import _get_git_diff
    diff, truncated = _get_git_diff(tmp_path)
    assert diff is None
    assert not truncated


def test_get_git_diff_clean_git_repo(tmp_path):
    """Clean git repo (no changes) returns ('', False)."""
    import subprocess
    from arasul_tui.commands.agent_cmd import _get_git_diff

    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=tmp_path, capture_output=True)

    diff, truncated = _get_git_diff(tmp_path)
    assert diff == ""
    assert not truncated


def test_get_git_diff_with_changes(tmp_path):
    """Git repo with uncommitted changes returns the diff."""
    import subprocess
    from arasul_tui.commands.agent_cmd import _get_git_diff

    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True)

    # Create and commit a file
    (tmp_path / "hello.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)

    # Modify the file (creates an unstaged diff)
    (tmp_path / "hello.py").write_text("x = 2\n")

    diff, truncated = _get_git_diff(tmp_path)
    assert diff is not None
    assert "hello.py" in diff
    assert not truncated


def test_get_git_diff_truncates_large_diffs(tmp_path, monkeypatch):
    """Diffs larger than _MAX_REVIEW_DIFF_CHARS are truncated."""
    import subprocess
    from arasul_tui.commands import agent_cmd

    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, capture_output=True)
    (tmp_path / "f.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)

    monkeypatch.setattr(agent_cmd, "_MAX_REVIEW_DIFF_CHARS", 5)
    (tmp_path / "f.py").write_text("x = 99999\n")

    diff, truncated = agent_cmd._get_git_diff(tmp_path)
    assert truncated
    assert len(diff) == 5
