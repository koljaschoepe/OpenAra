"""Core agent loop for Open Ara.

Ties together the LLM client, tool engine, context manager, and approval flow.
The loop runs until the model signals end_turn, a tool error is unrecoverable,
or a hard guard (max tool calls) fires.

Usage:
    result = await run_agent(
        task="Fix the login bug in src/auth.py",
        project_path=Path("/my/project"),
    )
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from arasul_tui.agent.config import AgentConfig, load_agent_config
from arasul_tui.agent.context.budget import TokenBudget
from arasul_tui.agent.context.pruner import prune_conversation, truncate_tool_result
from arasul_tui.agent.context.repo_map import RepoMap
from arasul_tui.agent.llm import (
    ContextLimitError,
    LLMError,
    LLMResponse,
    ToolCall,
    chat,
    tool_result_message,
)
from arasul_tui.agent.tools import (
    TOOL_DEFINITIONS,
    ToolError,
    execute_tool,
    requires_approval,
)
from arasul_tui.agent.tools.file_tools import diff_for_approval

log = logging.getLogger(__name__)

_MAX_TOOL_CALLS = 30   # hard stop for runaway loops
_MAX_ITERATIONS = 20   # outer loop guard
_PRUNE_THRESHOLD = 0.80  # prune when 80% of budget is consumed

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

ApprovalCallback = Callable[[str, dict[str, Any], str], Awaitable[bool]]
"""(tool_name, arguments, preview_text) → True to approve, False to reject."""


@dataclass
class AgentCallbacks:
    """Optional hooks for streaming output. None = silent."""

    on_text_token: Callable[[str], None] | None = None
    on_tool_start: Callable[[str, dict], None] | None = None
    on_tool_result: Callable[[str, str], None] | None = None
    on_prune: Callable[[int], None] | None = None  # called with messages dropped
    on_error: Callable[[str], None] | None = None
    on_llm_start: Callable[[], None] | None = None  # fired before each LLM call

    def text_token(self, token: str) -> None:
        if self.on_text_token:
            self.on_text_token(token)

    def tool_start(self, name: str, args: dict) -> None:
        if self.on_tool_start:
            self.on_tool_start(name, args)

    def tool_result(self, name: str, result: str) -> None:
        if self.on_tool_result:
            self.on_tool_result(name, result)

    def prune(self, dropped: int) -> None:
        if self.on_prune:
            self.on_prune(dropped)

    def error(self, msg: str) -> None:
        if self.on_error:
            self.on_error(msg)

    def llm_start(self) -> None:
        if self.on_llm_start:
            self.on_llm_start()


@dataclass
class AgentResult:
    text: str
    tool_calls_made: int
    iterations: int
    tokens_used: int
    stopped_reason: str = "done"  # done | max_tool_calls | max_iterations | error


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_CORE = """\
You are Open Ara, an AI coding agent. You work in the user's project directory on {project_name}.

Rules:
- Read files before editing them. Use read_file first, then write_file with COMPLETE content.
- write_file always requires the full file — never partial snippets or diffs.
- After making changes, run the tests with run_command.
- Use search_files to locate relevant code before assuming file paths.
- Be concise. The user sees your tool calls; avoid re-describing what they already show."""

_CLAUDE_MD_MAX_CHARS = 12_000  # ≈ 3000 tokens — stays within our budget


def _read_claude_md(project_path: Path) -> str:
    """Return the project's CLAUDE.md content, or empty string if absent."""
    claude_file = project_path / "CLAUDE.md"
    if not claude_file.is_file():
        return ""
    try:
        content = claude_file.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""
    if not content:
        return ""
    if len(content) > _CLAUDE_MD_MAX_CHARS:
        content = content[:_CLAUDE_MD_MAX_CHARS] + "\n... (CLAUDE.md truncated)"
        log.debug("CLAUDE.md exceeds %d chars; truncated", _CLAUDE_MD_MAX_CHARS)
    return f"Project instructions (CLAUDE.md):\n{content}"


def _build_system_prompt(project_path: Path, repo_map_text: str, think: bool = True) -> str:
    parts = [_SYSTEM_CORE.format(project_name=project_path.name)]
    claude_md = _read_claude_md(project_path)
    if claude_md:
        parts.append(claude_md)
    parts.append(repo_map_text or "(empty project — no source files found)")
    system = "\n\n".join(parts)
    if not think:
        system += "\n/no_think"
    return system


# ---------------------------------------------------------------------------
# Default approval: auto-approve (used in tests and non-interactive mode)
# ---------------------------------------------------------------------------

async def _auto_approve(name: str, args: dict, preview: str) -> bool:
    return True


# ---------------------------------------------------------------------------
# Session — persists context across multiple agent turns
# ---------------------------------------------------------------------------

class AgentSession:
    """Maintains conversation history and budget across turns.

    Create once per interactive session; call run() for each follow-up task.
    run_agent() is a thin single-turn wrapper around this class.
    """

    def __init__(
        self,
        project_path: Path,
        config: AgentConfig | None = None,
        callbacks: AgentCallbacks | None = None,
        approval: ApprovalCallback | None = None,
        system_override: str | None = None,
        tools_override: list[dict] | None = None,
        initial_messages: list[dict] | None = None,
    ) -> None:
        self.project_path = project_path
        self.cfg = config or load_agent_config()
        self.cb = callbacks or AgentCallbacks()
        self.approve = approval or _auto_approve

        self.budget = TokenBudget(max_tokens=self.cfg.context_limit)
        self.messages: list[dict] = list(initial_messages) if initial_messages else []
        self._last_hint: str = ""
        self._has_system_override = system_override is not None
        self._tools: list[dict] | None = tools_override  # None → use TOOL_DEFINITIONS

        if system_override is not None:
            self.system = system_override + ("\n/no_think" if not self.cfg.think else "")
        else:
            # Build initial system prompt (no task hint yet)
            repo_map = RepoMap(project_path).render(token_budget=2048)
            self.system = _build_system_prompt(project_path, repo_map, think=self.cfg.think)
        self.budget.consume(self.system)

    async def run(self, task: str) -> AgentResult:
        """Execute one turn, continuing from prior conversation history."""
        # Re-render repo map when the task hint changes (skipped when system is overridden)
        if not self._has_system_override and task != self._last_hint:
            self._last_hint = task
            repo_map = RepoMap(self.project_path).render(token_budget=2048, hint=task)
            self.system = _build_system_prompt(self.project_path, repo_map, think=self.cfg.think)

        self.messages.append({"role": "user", "content": task})
        self.budget.consume(task)

        total_tool_calls = 0
        final_text = ""
        stopped_reason = "done"

        for iteration in range(_MAX_ITERATIONS):
            # --- Context budget guard ---
            if self.budget.utilization >= _PRUNE_THRESHOLD:
                before = len(self.messages)
                self.messages = prune_conversation(
                    self.messages,
                    max_tokens=int(self.cfg.context_limit * 0.55),
                    keep_last=6,
                )
                self.cb.prune(before - len(self.messages))

            # --- LLM call ---
            self.cb.llm_start()
            response = await _call_llm(self.messages, self.system, self.cfg, self.cb, tools=self._tools)

            if response is None:
                stopped_reason = "error"
                break

            self.messages.append(response.to_message())

            if response.stop_reason in ("end_turn", "max_tokens") or not response.has_tool_calls:
                final_text = response.text
                if response.stop_reason == "max_tokens":
                    log.warning("Model hit max_tokens — response may be incomplete")
                break

            # --- Tool calls ---
            if total_tool_calls >= _MAX_TOOL_CALLS:
                self.cb.error(f"Stopped: reached {_MAX_TOOL_CALLS} tool calls.")
                stopped_reason = "max_tool_calls"
                break

            tool_results: list[dict] = []
            for tc in response.tool_calls:
                if total_tool_calls >= _MAX_TOOL_CALLS:
                    break
                total_tool_calls += 1

                result_text = await _dispatch_tool(tc, self.project_path, self.cb, self.approve)
                self.budget.consume(result_text)
                tool_results.append(tool_result_message(tc.id, result_text))

            self.messages.extend(tool_results)

        else:
            stopped_reason = "max_iterations"
            self.cb.error(f"Stopped: reached {_MAX_ITERATIONS} iterations without completing.")

        return AgentResult(
            text=final_text,
            tool_calls_made=total_tool_calls,
            iterations=iteration + 1,
            tokens_used=self.budget.used,
            stopped_reason=stopped_reason,
        )


# ---------------------------------------------------------------------------
# Single-turn convenience wrapper (backward-compatible public API)
# ---------------------------------------------------------------------------

async def run_agent(
    task: str,
    project_path: Path,
    config: AgentConfig | None = None,
    callbacks: AgentCallbacks | None = None,
    approval: ApprovalCallback | None = None,
) -> AgentResult:
    """Single-turn wrapper — creates an AgentSession and runs one turn."""
    session = AgentSession(
        project_path,
        config=config,
        callbacks=callbacks,
        approval=approval,
    )
    return await session.run(task)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _call_llm(
    messages: list[dict],
    system: str,
    cfg: AgentConfig,
    cb: AgentCallbacks,
    tools: list[dict] | None = None,
) -> LLMResponse | None:
    """Call LLM with one automatic prune-and-retry on context overflow.

    tools=None uses TOOL_DEFINITIONS; tools=[] disables tool calling entirely.
    """
    _tools = tools if tools is not None else TOOL_DEFINITIONS
    try:
        return await chat(
            messages=messages,
            system=system,
            tools=_tools,
            config=cfg,
            on_token=cb.text_token,
        )
    except ContextLimitError:
        log.warning("Context limit hit — force-pruning and retrying")
        pruned = prune_conversation(messages, max_tokens=int(cfg.context_limit * 0.4))
        try:
            return await chat(
                messages=pruned,
                system=system,
                tools=_tools,
                config=cfg,
                on_token=cb.text_token,
            )
        except LLMError as exc:
            cb.error(f"LLM error after prune: {exc}")
            return None
    except LLMError as exc:
        cb.error(f"LLM error: {exc}")
        return None


async def _dispatch_tool(
    tc: ToolCall,
    project_path: Path,
    cb: AgentCallbacks,
    approve: ApprovalCallback,
) -> str:
    """Execute one tool call, handling approval and errors gracefully."""
    cb.tool_start(tc.name, tc.arguments)

    # --- Approval ---
    if requires_approval(tc.name, tc.arguments):
        preview = _build_preview(tc, project_path)
        approved = await approve(tc.name, tc.arguments, preview)
        if not approved:
            result = f"Tool call '{tc.name}' was rejected by the user."
            cb.tool_result(tc.name, result)
            return result

    # --- Execution ---
    try:
        result = await execute_tool(tc.name, tc.arguments, project_path)
    except ToolError as exc:
        result = f"Tool error in '{tc.name}': {exc}"
        log.warning(result)
    except Exception as exc:
        result = f"Unexpected error in '{tc.name}': {type(exc).__name__}: {exc}"
        log.exception("Unexpected tool error")

    result = truncate_tool_result(result, max_tokens=2000)
    cb.tool_result(tc.name, result)
    return result


def _build_preview(tc: ToolCall, project_path: Path) -> str:
    """Human-readable preview of what a tool call will do (for approval UI)."""
    if tc.name == "write_file":
        path = tc.arguments.get("path", "")
        content = tc.arguments.get("content", "")
        try:
            return diff_for_approval(path, content, project_path)
        except Exception:
            return f"Write {len(content)} chars to {path}"
    return str(tc.arguments)
