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
        log.warning("CLAUDE.md exceeds %d chars; truncated", _CLAUDE_MD_MAX_CHARS)
    return f"Project instructions (CLAUDE.md):\n{content}"


def _build_system_prompt(project_path: Path, repo_map_text: str) -> str:
    parts = [_SYSTEM_CORE.format(project_name=project_path.name)]
    claude_md = _read_claude_md(project_path)
    if claude_md:
        parts.append(claude_md)
    parts.append(repo_map_text or "(empty project — no source files found)")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Default approval: auto-approve (used in tests and non-interactive mode)
# ---------------------------------------------------------------------------

async def _auto_approve(name: str, args: dict, preview: str) -> bool:
    return True


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def run_agent(
    task: str,
    project_path: Path,
    config: AgentConfig | None = None,
    callbacks: AgentCallbacks | None = None,
    approval: ApprovalCallback | None = None,
) -> AgentResult:
    """Run the agent loop until the task is complete or a guard fires.

    *approval* is called before any destructive tool call. It receives the tool
    name, its arguments dict, and a human-readable preview (diff or command).
    Return True to allow, False to skip this tool call.
    """
    cfg = config or load_agent_config()
    cb = callbacks or AgentCallbacks()
    approve = approval or _auto_approve

    budget = TokenBudget(max_tokens=cfg.context_limit)
    repo_map = RepoMap(project_path).render(token_budget=2048, hint=task)
    system = _build_system_prompt(project_path, repo_map)
    budget.consume(system)

    messages: list[dict] = [{"role": "user", "content": task}]
    budget.consume(task)

    total_tool_calls = 0
    final_text = ""
    stopped_reason = "done"

    for iteration in range(_MAX_ITERATIONS):
        # --- Context budget guard ---
        if budget.utilization >= _PRUNE_THRESHOLD:
            before = len(messages)
            messages = prune_conversation(
                messages,
                max_tokens=int(cfg.context_limit * 0.55),
                keep_last=6,
            )
            cb.prune(before - len(messages))

        # --- LLM call ---
        response = await _call_llm(messages, system, cfg, cb)

        if response is None:
            stopped_reason = "error"
            break

        messages.append(response.to_message())

        if response.stop_reason in ("end_turn", "max_tokens") or not response.has_tool_calls:
            final_text = response.text
            if response.stop_reason == "max_tokens":
                log.warning("Model hit max_tokens — response may be incomplete")
            break

        # --- Tool calls ---
        if total_tool_calls >= _MAX_TOOL_CALLS:
            cb.error(f"Stopped: reached {_MAX_TOOL_CALLS} tool calls.")
            stopped_reason = "max_tool_calls"
            break

        tool_results: list[dict] = []
        for tc in response.tool_calls:
            if total_tool_calls >= _MAX_TOOL_CALLS:
                break
            total_tool_calls += 1

            result_text = await _dispatch_tool(tc, project_path, cb, approve)
            budget.consume(result_text)
            tool_results.append(tool_result_message(tc.id, result_text))

        messages.extend(tool_results)

    else:
        stopped_reason = "max_iterations"
        cb.error(f"Stopped: reached {_MAX_ITERATIONS} iterations without completing.")

    return AgentResult(
        text=final_text,
        tool_calls_made=total_tool_calls,
        iterations=iteration + 1,
        tokens_used=budget.used,
        stopped_reason=stopped_reason,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _call_llm(
    messages: list[dict],
    system: str,
    cfg: AgentConfig,
    cb: AgentCallbacks,
) -> LLMResponse | None:
    """Call LLM with one automatic prune-and-retry on context overflow."""
    try:
        return await chat(
            messages=messages,
            system=system,
            tools=TOOL_DEFINITIONS,
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
                tools=TOOL_DEFINITIONS,
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
