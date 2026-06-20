"""Conversation pruning for context window management.

When the conversation grows too long, we drop middle messages while
keeping the task framing (first user message) and recent context
(last N messages). A placeholder is inserted so the LLM knows history
was truncated — this prevents it from making assumptions about content
it never saw.

Strategy (in order of priority):
  1. Always keep: system prompt (handled outside, not in messages list)
  2. Always keep: first user message (the original task)
  3. Always keep: last *keep_last* messages (recent tool results + responses)
  4. Drop: everything in between
  5. Insert: a single assistant placeholder explaining the gap
"""

from __future__ import annotations

from arasul_tui.agent.llm import estimate_messages_tokens

_PRUNED_PLACEHOLDER = (
    "[Earlier conversation omitted to stay within context window. "
    "The original task is preserved above. Continue from the most recent messages below.]"
)


def prune_conversation(
    messages: list[dict],
    max_tokens: int,
    keep_last: int = 6,
) -> list[dict]:
    """Trim *messages* to fit within *max_tokens*.

    Always preserves the first message (original task) and the last
    *keep_last* messages. Inserts a placeholder where content was dropped.

    Returns a new list — does not modify the input.
    """
    if not messages:
        return []

    if estimate_messages_tokens(messages) <= max_tokens:
        return list(messages)

    first = messages[:1]
    last = messages[max(1, len(messages) - keep_last):]

    # Edge case: first and last overlap (short conversation)
    if len(messages) <= keep_last + 1:
        return list(messages)

    placeholder = {
        "role": "assistant",
        "content": _PRUNED_PLACEHOLDER,
    }

    # Always include the placeholder — the LLM must know history was dropped.
    # Even if the result still exceeds max_tokens, that's better than silently
    # feeding contradictory context.
    return first + [placeholder] + last


def truncate_tool_result(content: str, max_tokens: int = 2000) -> str:
    """Trim a single tool result string that would blow the budget on its own.

    Keeps the beginning (most useful) and appends a truncation notice.
    max_tokens here is per-result, not the whole conversation budget.
    """
    max_chars = max_tokens * 4
    if len(content) <= max_chars:
        return content
    kept = content[:max_chars]
    dropped = len(content) - max_chars
    return f"{kept}\n... [{dropped} chars truncated — use read_file with line ranges for large files]"
