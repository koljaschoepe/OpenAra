"""Token budget manager for the agent context window.

Tracks estimated token consumption and provides guards before
adding more content. Uses the same 4-chars-per-token heuristic
as llm.estimate_tokens — consistent across the whole codebase.

Usage:
    budget = TokenBudget(max_tokens=12_000)
    budget.consume(system_prompt)
    budget.consume(repo_map)

    # Before adding a tool result:
    if budget.can_fit(tool_output):
        messages.append(tool_result_message(id, tool_output))
        budget.consume(tool_output)
    else:
        # truncate or skip
"""

from __future__ import annotations

from dataclasses import dataclass, field

from arasul_tui.agent.llm import estimate_tokens


@dataclass
class TokenBudget:
    max_tokens: int
    _used: int = field(default=0, init=False)

    # ---------------------------------------------------------------------------
    # Public interface
    # ---------------------------------------------------------------------------

    @property
    def used(self) -> int:
        return self._used

    @property
    def remaining(self) -> int:
        return max(0, self.max_tokens - self._used)

    @property
    def utilization(self) -> float:
        """0.0–1.0 fraction of budget consumed."""
        return self._used / self.max_tokens if self.max_tokens else 0.0

    def can_fit(self, text: str, safety_margin: int = 500) -> bool:
        """Return True if *text* fits within the remaining budget minus *safety_margin*."""
        return estimate_tokens(text) <= self.remaining - safety_margin

    def consume(self, text: str) -> int:
        """Add *text*'s estimated token count to the running total.

        Returns the number of tokens consumed by this call.
        """
        cost = estimate_tokens(text)
        self._used += cost
        return cost

    def consume_messages(self, messages: list[dict]) -> int:
        """Consume tokens for a list of chat messages."""
        from arasul_tui.agent.llm import estimate_messages_tokens
        cost = estimate_messages_tokens(messages)
        self._used += cost
        return cost

    def reset(self) -> None:
        self._used = 0

    def snapshot(self) -> int:
        """Return current usage (for save/restore around tentative operations)."""
        return self._used

    def restore(self, snapshot: int) -> None:
        """Revert to a previous snapshot value."""
        self._used = snapshot

    # ---------------------------------------------------------------------------
    # Repr
    # ---------------------------------------------------------------------------

    def __str__(self) -> str:
        pct = self.utilization * 100
        return f"TokenBudget({self._used}/{self.max_tokens} tokens, {pct:.0f}%)"
