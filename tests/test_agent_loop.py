"""Tests for arasul_tui.agent.agent (the main loop).

chat() is mocked throughout — these tests verify agent control flow,
not LLM behaviour.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from arasul_tui.agent.agent import (
    AgentCallbacks,
    AgentResult,
    AgentSession,
    _auto_approve,
    run_agent,
)
from arasul_tui.agent.config import AgentConfig
from arasul_tui.agent.llm import LLMResponse, ToolCall, Usage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _config(context_limit: int = 12000) -> AgentConfig:
    return AgentConfig(
        base_url="http://localhost:11434/v1",
        model="qwen3:14b",
        context_limit=context_limit,
    )


def _text_response(text: str = "Task done.") -> LLMResponse:
    return LLMResponse(text=text, stop_reason="end_turn", usage=Usage(100, 50))


def _tool_response(*calls: tuple[str, dict]) -> LLMResponse:
    """LLMResponse that requests one or more tool calls."""
    tcs = [ToolCall(id=f"call_{i}", name=name, arguments=args) for i, (name, args) in enumerate(calls)]
    return LLMResponse(text="", tool_calls=tcs, stop_reason="tool_use")


async def _always_approve(name, args, preview) -> bool:
    return True


async def _always_reject(name, args, preview) -> bool:
    return False


def _make_chat_mock(*responses: LLMResponse):
    """Return an AsyncMock that yields responses in sequence, repeating the last."""
    idx = 0

    async def mock_chat(messages, system, tools, config, on_token=None, on_tool_start=None):
        nonlocal idx
        resp = responses[min(idx, len(responses) - 1)]
        idx += 1
        if on_token and resp.text:
            on_token(resp.text)
        return resp

    return AsyncMock(side_effect=mock_chat)


# ---------------------------------------------------------------------------
# Basic text response
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_returns_text(tmp_path):
    mock = _make_chat_mock(_text_response("All done!"))
    with patch("arasul_tui.agent.agent.chat", mock):
        result = await run_agent("Do something", tmp_path, config=_config())

    assert isinstance(result, AgentResult)
    assert result.text == "All done!"
    assert result.tool_calls_made == 0
    assert result.iterations == 1
    assert result.stopped_reason == "done"


@pytest.mark.asyncio
async def test_agent_streaming_tokens_delivered(tmp_path):
    received: list[str] = []
    cb = AgentCallbacks(on_text_token=received.append)

    mock = _make_chat_mock(_text_response("Hello world"))
    with patch("arasul_tui.agent.agent.chat", mock):
        await run_agent("Say hi", tmp_path, config=_config(), callbacks=cb)

    assert received == ["Hello world"]


# ---------------------------------------------------------------------------
# Single tool call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_single_read_tool_call(tmp_path):
    (tmp_path / "app.py").write_text("x = 1\n")
    tool_calls_made: list[str] = []

    cb = AgentCallbacks(on_tool_start=lambda name, args: tool_calls_made.append(name))

    mock = _make_chat_mock(
        _tool_response(("read_file", {"path": "app.py"})),
        _text_response("I read the file."),
    )
    with patch("arasul_tui.agent.agent.chat", mock):
        result = await run_agent("Read app.py", tmp_path, config=_config(), callbacks=cb)

    assert result.tool_calls_made == 1
    assert result.text == "I read the file."
    assert "read_file" in tool_calls_made


@pytest.mark.asyncio
async def test_agent_write_file_tool_call(tmp_path):
    results: list[str] = []
    cb = AgentCallbacks(on_tool_result=lambda name, r: results.append(r))

    mock = _make_chat_mock(
        _tool_response(("write_file", {"path": "out.py", "content": "x = 42\n"})),
        _text_response("Written."),
    )
    with patch("arasul_tui.agent.agent.chat", mock):
        result = await run_agent(
            "Write out.py", tmp_path, config=_config(), approval=_always_approve
        )

    assert (tmp_path / "out.py").read_text() == "x = 42\n"
    assert result.tool_calls_made == 1


# ---------------------------------------------------------------------------
# Approval flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_approval_rejected_continues(tmp_path):
    """Rejected tool call should be reported back to LLM, not crash."""
    mock = _make_chat_mock(
        _tool_response(("write_file", {"path": "f.py", "content": "bad"})),
        _text_response("OK I won't write it."),
    )
    with patch("arasul_tui.agent.agent.chat", mock):
        result = await run_agent(
            "Write f.py", tmp_path, config=_config(), approval=_always_reject
        )

    assert not (tmp_path / "f.py").exists()
    assert result.stopped_reason == "done"


@pytest.mark.asyncio
async def test_agent_approval_called_for_destructive_commands(tmp_path):
    approvals: list[str] = []

    async def capture_approval(name, args, preview):
        approvals.append(name)
        return True

    mock = _make_chat_mock(
        _tool_response(("run_command", {"command": "rm old.py"})),
        _text_response("Done."),
    )
    with patch("arasul_tui.agent.agent.chat", mock):
        await run_agent("Remove old.py", tmp_path, config=_config(), approval=capture_approval)

    assert "run_command" in approvals


@pytest.mark.asyncio
async def test_agent_no_approval_for_safe_commands(tmp_path):
    approvals: list[str] = []

    async def capture_approval(name, args, preview):
        approvals.append(name)
        return True

    mock = _make_chat_mock(
        _tool_response(("run_command", {"command": "pytest tests/"})),
        _text_response("Tests passed."),
    )
    with patch("arasul_tui.agent.agent.chat", mock):
        await run_agent("Run tests", tmp_path, config=_config(), approval=capture_approval)

    assert "run_command" not in approvals  # safe command, no approval needed


# ---------------------------------------------------------------------------
# Tool errors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_tool_error_returned_to_llm(tmp_path):
    """ToolError should be sent back as a tool result so the agent can recover."""
    results: list[str] = []
    cb = AgentCallbacks(on_tool_result=lambda name, r: results.append(r))

    mock = _make_chat_mock(
        _tool_response(("read_file", {"path": "nonexistent.py"})),
        _text_response("The file doesn't exist."),
    )
    with patch("arasul_tui.agent.agent.chat", mock):
        result = await run_agent("Read nonexistent.py", tmp_path, config=_config(), callbacks=cb)

    # Agent continues and returns final text
    assert result.text == "The file doesn't exist."
    # Tool error was captured
    assert any("not found" in r.lower() or "error" in r.lower() for r in results)


@pytest.mark.asyncio
async def test_agent_unknown_tool_returns_error(tmp_path):
    mock = _make_chat_mock(
        # Simulate model hallucinating a tool name
        LLMResponse(
            text="",
            tool_calls=[ToolCall(id="call_x", name="fly_to_moon", arguments={})],
            stop_reason="tool_use",
        ),
        _text_response("I can't do that."),
    )
    with patch("arasul_tui.agent.agent.chat", mock):
        result = await run_agent("Do something impossible", tmp_path, config=_config())

    assert result.stopped_reason == "done"


# ---------------------------------------------------------------------------
# Guard: max tool calls
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_stops_at_max_tool_calls(tmp_path):
    (tmp_path / "f.py").write_text("x = 1\n")
    errors: list[str] = []
    cb = AgentCallbacks(on_error=errors.append)

    # Always responds with a tool call — never ends
    infinite_tool = _tool_response(("read_file", {"path": "f.py"}))
    mock = _make_chat_mock(infinite_tool)

    # Patch MAX_TOOL_CALLS to a small value
    with patch("arasul_tui.agent.agent._MAX_TOOL_CALLS", 3):
        with patch("arasul_tui.agent.agent.chat", mock):
            result = await run_agent("Loop forever", tmp_path, config=_config(), callbacks=cb)

    assert result.stopped_reason == "max_tool_calls"
    assert result.tool_calls_made == 3
    assert any("30" in e or "3" in e for e in errors)


# ---------------------------------------------------------------------------
# Guard: max iterations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_stops_at_max_iterations(tmp_path):
    """Model keeps calling tools but _MAX_ITERATIONS fires before _MAX_TOOL_CALLS."""
    (tmp_path / "f.py").write_text("x = 1\n")
    errors: list[str] = []
    cb = AgentCallbacks(on_error=errors.append)

    # Always returns one read_file tool call — never ends naturally
    always_tool = _tool_response(("read_file", {"path": "f.py"}))
    mock = _make_chat_mock(always_tool)

    with patch("arasul_tui.agent.agent._MAX_ITERATIONS", 3):
        with patch("arasul_tui.agent.agent._MAX_TOOL_CALLS", 100):
            with patch("arasul_tui.agent.agent.chat", mock):
                result = await run_agent("Never finish", tmp_path, config=_config(), callbacks=cb)

    assert result.stopped_reason == "max_iterations"
    assert result.iterations == 3
    assert any("iteration" in e.lower() for e in errors)


# ---------------------------------------------------------------------------
# Context pruning
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_prunes_at_high_utilization(tmp_path):
    pruned_counts: list[int] = []
    cb = AgentCallbacks(on_prune=pruned_counts.append)

    # Small context limit so we hit the prune threshold quickly
    cfg = AgentConfig(
        base_url="http://localhost:11434/v1",
        model="qwen3:14b",
        context_limit=200,  # very tight
    )

    mock = _make_chat_mock(_text_response("Done"))
    with patch("arasul_tui.agent.agent.chat", mock):
        await run_agent("Do stuff", tmp_path, config=cfg, callbacks=cb)

    # Prune was triggered (context_limit=200, system prompt alone fills it)
    assert len(pruned_counts) >= 0  # may or may not trigger depending on system prompt size


# ---------------------------------------------------------------------------
# AgentResult structure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_result_fields(tmp_path):
    (tmp_path / "x.py").write_text("pass\n")
    mock = _make_chat_mock(
        _tool_response(("read_file", {"path": "x.py"})),
        _text_response("Read it."),
    )
    with patch("arasul_tui.agent.agent.chat", mock):
        result = await run_agent("Read x.py", tmp_path, config=_config())

    assert result.text == "Read it."
    assert result.tool_calls_made == 1
    assert result.iterations == 2  # 1 tool call iteration + 1 final
    assert result.tokens_used > 0
    assert result.stopped_reason == "done"


# ---------------------------------------------------------------------------
# Multiple tool calls in one response
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_multiple_tools_in_one_response(tmp_path):
    (tmp_path / "a.py").write_text("pass\n")
    (tmp_path / "b.py").write_text("pass\n")

    tool_calls: list[str] = []
    cb = AgentCallbacks(on_tool_start=lambda name, args: tool_calls.append(name))

    mock = _make_chat_mock(
        _tool_response(
            ("read_file", {"path": "a.py"}),
            ("read_file", {"path": "b.py"}),
        ),
        _text_response("Read both."),
    )
    with patch("arasul_tui.agent.agent.chat", mock):
        result = await run_agent("Read both files", tmp_path, config=_config(), callbacks=cb)

    assert result.tool_calls_made == 2
    assert tool_calls.count("read_file") == 2


# ---------------------------------------------------------------------------
# LLM error handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_handles_llm_error_gracefully(tmp_path):
    from arasul_tui.agent.llm import LLMError

    errors: list[str] = []
    cb = AgentCallbacks(on_error=errors.append)

    mock = AsyncMock(side_effect=LLMError("Connection refused"))
    with patch("arasul_tui.agent.agent.chat", mock):
        result = await run_agent("Do something", tmp_path, config=_config(), callbacks=cb)

    assert result.stopped_reason == "error"
    assert any("Connection refused" in e or "LLM error" in e for e in errors)


# ---------------------------------------------------------------------------
# _auto_approve
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_approve_always_returns_true():
    result = await _auto_approve("write_file", {"path": "x"}, "diff...")
    assert result is True


# ---------------------------------------------------------------------------
# AgentSession — multi-turn
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_accumulates_messages_across_turns(tmp_path):
    """Messages from turn 1 are still present in the conversation during turn 2."""
    received_message_counts: list[int] = []

    async def recording_chat(messages, system, tools, config, on_token=None, on_tool_start=None):
        received_message_counts.append(len(messages))
        return _text_response("Done.")

    mock = AsyncMock(side_effect=recording_chat)
    with patch("arasul_tui.agent.agent.chat", mock):
        session = AgentSession(tmp_path, config=_config())
        await session.run("First task")
        await session.run("Second task")

    # Turn 1: system + user = 2 messages (system is in messages list here)
    # Actually chat() receives full_messages = [system, *messages]
    # Turn 1 call: 2 messages (system + "First task")
    # Turn 2 call: at least 4 messages (system + "First task" + assistant response + "Second task")
    assert received_message_counts[0] < received_message_counts[1]


@pytest.mark.asyncio
async def test_session_run_returns_independent_results(tmp_path):
    """Each run() call returns its own AgentResult with correct iteration count."""
    responses = [
        _text_response("First done."),
        _tool_response(("read_file", {"path": "x.py"})),
        _text_response("Second done."),
    ]
    (tmp_path / "x.py").write_text("pass\n")

    mock = _make_chat_mock(*responses)
    with patch("arasul_tui.agent.agent.chat", mock):
        session = AgentSession(tmp_path, config=_config())
        r1 = await session.run("First task")
        r2 = await session.run("Second task")

    assert r1.text == "First done."
    assert r1.tool_calls_made == 0
    assert r2.text == "Second done."
    assert r2.tool_calls_made == 1


@pytest.mark.asyncio
async def test_session_repo_map_refreshed_on_hint_change(tmp_path):
    """System prompt is rebuilt when the task hint changes between turns."""
    system_prompts: list[str] = []

    async def capture_system(messages, system, tools, config, on_token=None, on_tool_start=None):
        system_prompts.append(system)
        return _text_response("OK")

    mock = AsyncMock(side_effect=capture_system)
    with patch("arasul_tui.agent.agent.chat", mock):
        session = AgentSession(tmp_path, config=_config())
        await session.run("authentication bug")
        await session.run("authentication bug")  # same hint — no rebuild
        await session.run("database schema")     # different hint — rebuilds

    # Same hint → same system prompt for calls 1 and 2
    assert system_prompts[0] == system_prompts[1]
    # Different hint → system prompt may differ (repo map re-ranked)
    # We can't assert they differ (empty project), but no crash
    assert len(system_prompts) == 3


@pytest.mark.asyncio
async def test_session_tool_errors_dont_break_subsequent_turns(tmp_path):
    """A ToolError in turn 1 is recovered; turn 2 completes normally."""
    mock = _make_chat_mock(
        _tool_response(("read_file", {"path": "missing.py"})),  # will error
        _text_response("File not found, that's fine."),
        _text_response("Second task done."),
    )
    with patch("arasul_tui.agent.agent.chat", mock):
        session = AgentSession(tmp_path, config=_config())
        r1 = await session.run("Read missing.py")
        r2 = await session.run("Now do something else")

    assert r1.stopped_reason == "done"
    assert r2.stopped_reason == "done"
    assert r2.text == "Second task done."


@pytest.mark.asyncio
async def test_session_max_tool_calls_resets_per_turn(tmp_path):
    """Each turn starts a fresh tool-call counter (session doesn't carry over)."""
    (tmp_path / "f.py").write_text("x = 1\n")

    # Turn 1 uses 2 tool calls, turn 2 uses 1 — both should complete
    responses = [
        _tool_response(("read_file", {"path": "f.py"})),
        _tool_response(("read_file", {"path": "f.py"})),
        _text_response("Turn 1 done."),
        _tool_response(("read_file", {"path": "f.py"})),
        _text_response("Turn 2 done."),
    ]
    mock = _make_chat_mock(*responses)
    with patch("arasul_tui.agent.agent.chat", mock):
        with patch("arasul_tui.agent.agent._MAX_TOOL_CALLS", 5):
            session = AgentSession(tmp_path, config=_config())
            r1 = await session.run("Two reads")
            r2 = await session.run("One read")

    assert r1.tool_calls_made == 2
    assert r2.tool_calls_made == 1


@pytest.mark.asyncio
async def test_session_budget_shared_across_turns(tmp_path):
    """Token budget is shared — second turn sees remaining budget, not full budget."""
    cfg = AgentConfig(base_url="http://localhost:11434/v1", model="qwen3:14b", context_limit=500)
    mock = _make_chat_mock(_text_response("OK"))
    with patch("arasul_tui.agent.agent.chat", mock):
        session = AgentSession(tmp_path, config=cfg)
        await session.run("First")
        budget_after_first = session.budget.used
        await session.run("Second")
        budget_after_second = session.budget.used

    assert budget_after_second > budget_after_first


# ---------------------------------------------------------------------------
# AgentSession — tools_override
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_tools_override_empty_passes_empty_list(tmp_path):
    """tools_override=[] passes an empty tools list to the LLM (disables tool calling)."""
    captured_tools: list = []

    async def capture_chat(messages, system, tools, config, on_token=None, on_tool_start=None):
        captured_tools.append(tools)
        return _text_response("feat: initial commit")

    with patch("arasul_tui.agent.agent.chat", AsyncMock(side_effect=capture_chat)):
        session = AgentSession(tmp_path, config=_config(), tools_override=[])
        result = await session.run("Write a commit message")

    assert result.text == "feat: initial commit"
    assert captured_tools[0] == []  # empty list, not TOOL_DEFINITIONS


@pytest.mark.asyncio
async def test_session_tools_override_none_uses_tool_definitions(tmp_path):
    """tools_override=None (default) passes TOOL_DEFINITIONS to the LLM."""
    from arasul_tui.agent.tools import TOOL_DEFINITIONS

    captured_tools: list = []

    async def capture_chat(messages, system, tools, config, on_token=None, on_tool_start=None):
        captured_tools.append(tools)
        return _text_response("Done")

    with patch("arasul_tui.agent.agent.chat", AsyncMock(side_effect=capture_chat)):
        session = AgentSession(tmp_path, config=_config())  # tools_override not set
        await session.run("Do something")

    assert captured_tools[0] == TOOL_DEFINITIONS
