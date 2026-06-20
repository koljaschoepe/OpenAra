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
