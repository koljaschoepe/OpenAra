"""LLM client for Open Ara agent — OpenAI-compatible, Ollama-first.

Handles streaming, tool-call accumulation, and retry with backoff.
Designed for local 14B models: low temperature, defensive JSON parsing,
3-attempt retry on transient failures.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

try:
    from openai import (
        AsyncOpenAI,
        BadRequestError,
        NotFoundError,
        APIConnectionError,
        APITimeoutError,
        InternalServerError,
    )
    _OPENAI_AVAILABLE = True
except ImportError:
    _OPENAI_AVAILABLE = False

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]

    def to_message_part(self) -> dict:
        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.name, "arguments": json.dumps(self.arguments)},
        }


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class LLMResponse:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"
    usage: Usage = field(default_factory=Usage)

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)

    def to_message(self) -> dict:
        msg: dict[str, Any] = {"role": "assistant"}
        if self.text:
            msg["content"] = self.text
        if self.tool_calls:
            msg["tool_calls"] = [tc.to_message_part() for tc in self.tool_calls]
        return msg


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class LLMError(Exception):
    pass


class ContextLimitError(LLMError):
    """Prompt exceeded the model's context window — do not retry."""


class ModelNotFoundError(LLMError):
    """Model name not found in Ollama — do not retry."""


class ToolCallParseError(LLMError):
    """Model returned malformed JSON in a tool call — retryable."""


# ---------------------------------------------------------------------------
# Internal: stream accumulation
# ---------------------------------------------------------------------------


@dataclass
class _PartialToolCall:
    id: str = ""
    name: str = ""
    arguments_buf: str = ""


def _finalize_tool_calls(partials: dict[int, _PartialToolCall]) -> list[ToolCall]:
    result: list[ToolCall] = []
    for idx in sorted(partials):
        p = partials[idx]
        if not p.name:
            continue
        try:
            args = json.loads(p.arguments_buf or "{}")
        except json.JSONDecodeError as exc:
            raise ToolCallParseError(
                f"Tool '{p.name}' returned invalid JSON: {p.arguments_buf!r}"
            ) from exc
        result.append(ToolCall(id=p.id, name=p.name, arguments=args))
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# Type alias for streaming callbacks
OnToken = Callable[[str], None]
OnToolStart = Callable[[str, str], None]  # (tool_name, call_id)


async def chat(
    messages: list[dict],
    system: str,
    tools: list[dict],
    config: "AgentConfig",  # noqa: F821 — imported at call site
    on_token: OnToken | None = None,
    on_tool_start: OnToolStart | None = None,
) -> LLMResponse:
    """Send a chat request to Ollama and return the complete response.

    Streams tokens via *on_token* and notifies tool-call starts via
    *on_tool_start*. Retries up to 3 times on transient failures.
    """
    if not _OPENAI_AVAILABLE:
        raise LLMError("openai package not installed. Run: pip install openai")

    client = AsyncOpenAI(
        base_url=config.base_url,
        api_key="ollama",
        timeout=120.0,
    )

    full_messages = [{"role": "system", "content": system}, *messages]

    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = await _do_stream(
                client=client,
                messages=full_messages,
                tools=tools,
                config=config,
                on_token=on_token,
                on_tool_start=on_tool_start,
            )
            return response

        except ToolCallParseError:
            # Model produced bad JSON — retry gives it another chance
            last_error = ToolCallParseError(
                f"Tool call JSON parse failed (attempt {attempt + 1}/3)"
            )
            log.warning("Tool call parse error on attempt %d/3", attempt + 1)
            if attempt < 2:
                await asyncio.sleep(0.5 * (attempt + 1))

        except (APIConnectionError, APITimeoutError, InternalServerError) as exc:  # type: ignore[misc]
            last_error = exc
            log.warning("Transient error on attempt %d/3: %s", attempt + 1, exc)
            if attempt < 2:
                await asyncio.sleep(1.0 * (attempt + 1))

        except BadRequestError as exc:  # type: ignore[misc]
            msg = str(exc).lower()
            if "context" in msg or "too long" in msg or "maximum" in msg:
                raise ContextLimitError(
                    f"Context window exceeded ({config.context_limit} tokens). "
                    "Reduce conversation history or repo map size."
                ) from exc
            raise LLMError(str(exc)) from exc

        except NotFoundError as exc:  # type: ignore[misc]
            raise ModelNotFoundError(
                f"Model '{config.model}' not found at {config.base_url}. "
                "Check that Ollama is running and the model is pulled."
            ) from exc

    raise LLMError(f"LLM call failed after 3 attempts") from last_error


async def _do_stream(
    client: Any,
    messages: list[dict],
    tools: list[dict],
    config: Any,
    on_token: OnToken | None,
    on_tool_start: OnToolStart | None,
) -> LLMResponse:
    response = LLMResponse()
    partial_tool_calls: dict[int, _PartialToolCall] = {}
    notified_tool_ids: set[str] = set()

    num_ctx = getattr(config, "num_ctx", 16384)
    stream = await client.chat.completions.create(
        model=config.model,
        messages=messages,
        tools=tools if tools else None,
        stream=True,
        temperature=config.temperature,
        max_tokens=config.max_output_tokens,
        extra_body={"options": {"num_ctx": num_ctx}},
    )

    async for chunk in stream:
        choice = chunk.choices[0] if chunk.choices else None
        if choice is None:
            continue

        delta = choice.delta

        # Text token
        if delta.content:
            response.text += delta.content
            if on_token:
                on_token(delta.content)

        # Tool call chunks — accumulate per index
        if delta.tool_calls:
            for tc_delta in delta.tool_calls:
                idx = tc_delta.index
                if idx not in partial_tool_calls:
                    partial_tool_calls[idx] = _PartialToolCall()

                partial = partial_tool_calls[idx]
                if tc_delta.id:
                    partial.id = tc_delta.id
                if tc_delta.function:
                    if tc_delta.function.name:
                        partial.name = tc_delta.function.name
                    if tc_delta.function.arguments:
                        partial.arguments_buf += tc_delta.function.arguments

                # Notify as soon as we have name + id
                if (
                    partial.id
                    and partial.name
                    and partial.id not in notified_tool_ids
                    and on_tool_start
                ):
                    on_tool_start(partial.name, partial.id)
                    notified_tool_ids.add(partial.id)

        # Stop reason
        if choice.finish_reason:
            finish = choice.finish_reason
            if finish == "tool_calls":
                response.stop_reason = "tool_use"
            elif finish == "length":
                response.stop_reason = "max_tokens"
            elif finish == "stop":
                response.stop_reason = "end_turn"
            else:
                response.stop_reason = finish

        # Usage (usually in last chunk)
        if chunk.usage:
            response.usage = Usage(
                input_tokens=chunk.usage.prompt_tokens or 0,
                output_tokens=chunk.usage.completion_tokens or 0,
            )

    # Finalize tool calls (parses accumulated JSON — may raise ToolCallParseError)
    if partial_tool_calls:
        response.tool_calls = _finalize_tool_calls(partial_tool_calls)

    return response


# ---------------------------------------------------------------------------
# Helpers used by the agent loop
# ---------------------------------------------------------------------------


def tool_result_message(tool_call_id: str, content: str) -> dict:
    """Build a tool-result message for the next LLM call."""
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": content,
    }


def estimate_tokens(text: str) -> int:
    """Fast token estimate: 1 token ≈ 4 chars (good enough for budget tracking)."""
    return max(1, len(text) // 4)


def estimate_messages_tokens(messages: list[dict]) -> int:
    total = 0
    for msg in messages:
        content = msg.get("content") or ""
        if isinstance(content, str):
            total += estimate_tokens(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    total += estimate_tokens(str(part))
    return total
