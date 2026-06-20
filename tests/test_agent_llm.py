"""Tests for arasul_tui.agent.llm.

Unit tests use mocked openai responses and run offline.
The live_* tests hit a real Ollama endpoint — skip unless OLLAMA_BASE_URL is set.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from arasul_tui.agent.llm import (
    LLMResponse,
    ToolCall,
    ToolCallParseError,
    Usage,
    _PartialToolCall,
    _finalize_tool_calls,
    estimate_messages_tokens,
    estimate_tokens,
    tool_result_message,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@dataclass
class _MockConfig:
    base_url: str = "http://localhost:11434/v1"
    model: str = "qwen3:14b"
    context_limit: int = 12000
    temperature: float = 0.1
    max_output_tokens: int = 4096


MOCK_CONFIG = _MockConfig()

SIMPLE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    }
]


# ---------------------------------------------------------------------------
# Unit: _finalize_tool_calls
# ---------------------------------------------------------------------------


def test_finalize_single_tool_call():
    partials = {
        0: _PartialToolCall(id="call_abc", name="read_file", arguments_buf='{"path": "main.py"}')
    }
    result = _finalize_tool_calls(partials)
    assert len(result) == 1
    assert result[0].id == "call_abc"
    assert result[0].name == "read_file"
    assert result[0].arguments == {"path": "main.py"}


def test_finalize_multiple_tool_calls():
    partials = {
        0: _PartialToolCall(id="call_1", name="read_file", arguments_buf='{"path": "a.py"}'),
        1: _PartialToolCall(id="call_2", name="list_files", arguments_buf='{"path": "."}'),
    }
    result = _finalize_tool_calls(partials)
    assert len(result) == 2
    assert result[0].name == "read_file"
    assert result[1].name == "list_files"


def test_finalize_empty_arguments():
    partials = {0: _PartialToolCall(id="call_x", name="list_files", arguments_buf="")}
    result = _finalize_tool_calls(partials)
    assert result[0].arguments == {}


def test_finalize_invalid_json_raises():
    partials = {0: _PartialToolCall(id="call_x", name="read_file", arguments_buf="{broken")}
    with pytest.raises(ToolCallParseError, match="invalid JSON"):
        _finalize_tool_calls(partials)


def test_finalize_skips_nameless_partial():
    partials = {0: _PartialToolCall(id="call_x", name="", arguments_buf="{}")}
    result = _finalize_tool_calls(partials)
    assert result == []


# ---------------------------------------------------------------------------
# Unit: ToolCall.to_message_part
# ---------------------------------------------------------------------------


def test_tool_call_to_message_part():
    tc = ToolCall(id="call_1", name="read_file", arguments={"path": "main.py"})
    part = tc.to_message_part()
    assert part["id"] == "call_1"
    assert part["type"] == "function"
    assert json.loads(part["function"]["arguments"]) == {"path": "main.py"}


# ---------------------------------------------------------------------------
# Unit: LLMResponse.to_message
# ---------------------------------------------------------------------------


def test_llm_response_to_message_text_only():
    r = LLMResponse(text="Hello!", stop_reason="end_turn")
    msg = r.to_message()
    assert msg["role"] == "assistant"
    assert msg["content"] == "Hello!"
    assert "tool_calls" not in msg


def test_llm_response_to_message_with_tool_calls():
    tc = ToolCall(id="call_1", name="read_file", arguments={"path": "x.py"})
    r = LLMResponse(text="", tool_calls=[tc], stop_reason="tool_use")
    msg = r.to_message()
    assert "tool_calls" in msg
    assert len(msg["tool_calls"]) == 1


def test_llm_response_has_tool_calls():
    r = LLMResponse(tool_calls=[ToolCall("id", "name", {})])
    assert r.has_tool_calls is True

    r2 = LLMResponse()
    assert r2.has_tool_calls is False


# ---------------------------------------------------------------------------
# Unit: tool_result_message
# ---------------------------------------------------------------------------


def test_tool_result_message():
    msg = tool_result_message("call_123", "file content here")
    assert msg["role"] == "tool"
    assert msg["tool_call_id"] == "call_123"
    assert msg["content"] == "file content here"


# ---------------------------------------------------------------------------
# Unit: token estimation
# ---------------------------------------------------------------------------


def test_estimate_tokens_basic():
    assert estimate_tokens("") >= 1
    assert estimate_tokens("hello") == 1      # 5 chars → 1
    assert estimate_tokens("a" * 400) == 100  # 400 chars → 100


def test_estimate_messages_tokens():
    messages = [
        {"role": "user", "content": "a" * 400},
        {"role": "assistant", "content": "b" * 200},
    ]
    total = estimate_messages_tokens(messages)
    assert total == 150  # 100 + 50


# ---------------------------------------------------------------------------
# Unit: chat() — mocked OpenAI stream
# ---------------------------------------------------------------------------


def _make_chunk(content=None, tool_calls=None, finish_reason=None, usage=None):
    chunk = MagicMock()
    chunk.choices = [MagicMock()]
    chunk.choices[0].delta.content = content
    chunk.choices[0].delta.tool_calls = tool_calls
    chunk.choices[0].finish_reason = finish_reason
    chunk.usage = usage
    return chunk


async def _async_iter(items):
    for item in items:
        yield item


@pytest.mark.asyncio
async def test_chat_text_response():
    chunks = [
        _make_chunk(content="Hello"),
        _make_chunk(content=" world"),
        _make_chunk(finish_reason="stop"),
    ]

    tokens_received = []

    with patch("arasul_tui.agent.llm.AsyncOpenAI") as MockClient:
        instance = MockClient.return_value
        instance.chat.completions.create = AsyncMock(
            return_value=_async_iter(chunks)
        )

        from arasul_tui.agent.llm import chat

        result = await chat(
            messages=[{"role": "user", "content": "hi"}],
            system="You are helpful.",
            tools=[],
            config=MOCK_CONFIG,
            on_token=tokens_received.append,
        )

    assert result.text == "Hello world"
    assert result.stop_reason == "end_turn"
    assert result.has_tool_calls is False
    assert tokens_received == ["Hello", " world"]


@pytest.mark.asyncio
async def test_chat_tool_call_response():
    tc_chunk1 = MagicMock()
    tc_chunk1.index = 0
    tc_chunk1.id = "call_abc"
    tc_chunk1.function.name = "read_file"
    tc_chunk1.function.arguments = '{"path"'

    tc_chunk2 = MagicMock()
    tc_chunk2.index = 0
    tc_chunk2.id = None
    tc_chunk2.function.name = None
    tc_chunk2.function.arguments = ': "main.py"}'

    chunks = [
        _make_chunk(tool_calls=[tc_chunk1]),
        _make_chunk(tool_calls=[tc_chunk2]),
        _make_chunk(finish_reason="tool_calls"),
    ]

    tool_starts = []

    with patch("arasul_tui.agent.llm.AsyncOpenAI") as MockClient:
        instance = MockClient.return_value
        instance.chat.completions.create = AsyncMock(
            return_value=_async_iter(chunks)
        )

        from arasul_tui.agent.llm import chat

        result = await chat(
            messages=[{"role": "user", "content": "read main.py"}],
            system="You are helpful.",
            tools=SIMPLE_TOOLS,
            config=MOCK_CONFIG,
            on_tool_start=lambda name, id: tool_starts.append(name),
        )

    assert result.stop_reason == "tool_use"
    assert result.has_tool_calls is True
    assert result.tool_calls[0].name == "read_file"
    assert result.tool_calls[0].arguments == {"path": "main.py"}
    assert "read_file" in tool_starts


@pytest.mark.asyncio
async def test_chat_retries_on_parse_error():
    bad_tc = MagicMock()
    bad_tc.index = 0
    bad_tc.id = "call_x"
    bad_tc.function.name = "read_file"
    bad_tc.function.arguments = "{broken json"

    bad_chunks = [
        _make_chunk(tool_calls=[bad_tc]),
        _make_chunk(finish_reason="tool_calls"),
    ]

    with patch("arasul_tui.agent.llm.AsyncOpenAI") as MockClient:
        with patch("arasul_tui.agent.llm.asyncio.sleep", new_callable=AsyncMock):
            instance = MockClient.return_value
            # Return a fresh generator each call — exhausted generators yield nothing
            async def _fresh_stream(*_a, **_kw):
                for chunk in bad_chunks:
                    yield chunk

            instance.chat.completions.create = AsyncMock(
                side_effect=lambda *a, **kw: _fresh_stream(*a, **kw)
            )

            from arasul_tui.agent.llm import LLMError, chat

            with pytest.raises(LLMError, match="3 attempts"):
                await chat(
                    messages=[{"role": "user", "content": "read"}],
                    system="",
                    tools=SIMPLE_TOOLS,
                    config=MOCK_CONFIG,
                )

            # Should have been called 3 times (original + 2 retries)
            assert instance.chat.completions.create.call_count == 3


@pytest.mark.asyncio
async def test_chat_raises_context_limit_error():
    from openai import BadRequestError

    with patch("arasul_tui.agent.llm.AsyncOpenAI") as MockClient:
        instance = MockClient.return_value
        instance.chat.completions.create = AsyncMock(
            side_effect=BadRequestError(
                message="context window exceeded",
                response=MagicMock(status_code=400),
                body={"error": {"message": "context window exceeded"}},
            )
        )

        from arasul_tui.agent.llm import ContextLimitError, chat

        with pytest.raises(ContextLimitError):
            await chat(
                messages=[{"role": "user", "content": "hi"}],
                system="",
                tools=[],
                config=MOCK_CONFIG,
            )


@pytest.mark.asyncio
async def test_chat_raises_model_not_found():
    from openai import NotFoundError

    with patch("arasul_tui.agent.llm.AsyncOpenAI") as MockClient:
        instance = MockClient.return_value
        instance.chat.completions.create = AsyncMock(
            side_effect=NotFoundError(
                message="model not found",
                response=MagicMock(status_code=404),
                body={},
            )
        )

        from arasul_tui.agent.llm import ModelNotFoundError, chat

        with pytest.raises(ModelNotFoundError, match="qwen3:14b"):
            await chat(
                messages=[{"role": "user", "content": "hi"}],
                system="",
                tools=[],
                config=MOCK_CONFIG,
            )


# ---------------------------------------------------------------------------
# Live tests — require running Ollama
# ---------------------------------------------------------------------------

OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "")
skip_live = pytest.mark.skipif(not OLLAMA_URL, reason="OLLAMA_BASE_URL not set")


@dataclass
class _LiveConfig:
    base_url: str = OLLAMA_URL or "http://localhost:11434/v1"
    model: str = os.environ.get("OLLAMA_MODEL", "qwen3:14b")
    context_limit: int = 12000
    temperature: float = 0.1
    max_output_tokens: int = 256


@skip_live
@pytest.mark.asyncio
async def test_live_simple_text():
    from arasul_tui.agent.llm import chat

    tokens = []
    result = await chat(
        messages=[{"role": "user", "content": "Reply with exactly: OK"}],
        system="You are a terse assistant. Reply with one word only.",
        tools=[],
        config=_LiveConfig(),
        on_token=tokens.append,
    )
    assert result.stop_reason == "end_turn"
    assert len(result.text) > 0
    assert len(tokens) > 0


@skip_live
@pytest.mark.asyncio
async def test_live_tool_call():
    from arasul_tui.agent.llm import chat

    result = await chat(
        messages=[{"role": "user", "content": "Read the file main.py"}],
        system="You are a coding agent. Use tools to help the user.",
        tools=SIMPLE_TOOLS,
        config=_LiveConfig(),
    )
    # Should either call the tool or explain it can't
    assert result.stop_reason in ("tool_use", "end_turn")
    if result.stop_reason == "tool_use":
        assert result.tool_calls[0].name == "read_file"
        assert "path" in result.tool_calls[0].arguments
