"""Chat UI for the Open Ara agent — rich-based terminal output.

Streams LLM tokens directly to stdout (bypasses Rich markup buffering for
low latency). All structured output (tool calls, approval prompts, stats)
uses the shared console/theme so it looks consistent with the rest of the TUI.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

from rich.syntax import Syntax

from arasul_tui.core.theme import DIM, ERROR, PRIMARY, SUCCESS, WARNING
from arasul_tui.core.ui import console, content_pad
from arasul_tui.agent.agent import AgentCallbacks, AgentResult

_TOOL_ICONS: dict[str, str] = {
    "read_file": "↓",
    "write_file": "↑",
    "run_command": "▶",
    "search_files": "⌕",
    "list_files": "≡",
}

_APPROVAL_REQUIRED = frozenset({"write_file", "run_command"})


def _arg_summary(name: str, args: dict[str, Any]) -> str:
    if name == "read_file":
        path = args.get("path", "")
        lo = args.get("start_line")
        hi = args.get("end_line")
        if lo or hi:
            return f"{path}:{lo or ''}–{hi or ''}"
        return path
    if name == "write_file":
        return args.get("path", "")
    if name == "run_command":
        cmd = args.get("command", "")
        return cmd[:60] + ("…" if len(cmd) > 60 else "")
    if name == "search_files":
        pattern = args.get("pattern", "")
        glob = args.get("file_pattern", "*")
        suffix = f" in {glob}" if glob != "*" else ""
        return f'"{pattern}"{suffix}'
    if name == "list_files":
        return args.get("path", ".")
    return str(args)[:60]


class ChatUI:
    """Manages all terminal output for one agent session."""

    def __init__(self, project_path: Path) -> None:
        self.project_path = project_path
        self._in_stream = False  # True while LLM tokens are flowing

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def print_header(self, task: str) -> None:
        pad = content_pad()
        console.print()
        console.print(
            f"{pad}[{PRIMARY}]◆ Open Ara[/{PRIMARY}]  "
            f"[dim]{self.project_path.name}[/dim]"
        )
        console.print(f"{pad}  {task}")
        console.print(f"{pad}[{DIM}]{'─' * 52}[/{DIM}]")
        console.print()

    def print_footer(self, result: AgentResult) -> None:
        self._end_stream()
        pad = content_pad()
        console.print()
        stop = result.stopped_reason
        if stop == "done":
            icon = f"[{SUCCESS}]✓[/{SUCCESS}]"
        elif stop in ("max_tool_calls", "max_iterations"):
            icon = f"[{WARNING}]~[/{WARNING}]"
        else:
            icon = f"[{ERROR}]✗[/{ERROR}]"
        console.print(
            f"{pad}{icon} [{DIM}]"
            f"{result.tool_calls_made} tool calls · "
            f"{result.iterations} iteration(s) · "
            f"~{result.tokens_used} tokens"
            f"[/{DIM}]"
        )

    # ------------------------------------------------------------------
    # Streaming output
    # ------------------------------------------------------------------

    def on_text_token(self, token: str) -> None:
        if not self._in_stream:
            self._in_stream = True
            sys.stdout.write(content_pad())  # indent first line
        sys.stdout.write(token)
        sys.stdout.flush()

    def _end_stream(self) -> None:
        if self._in_stream:
            sys.stdout.write("\n")
            sys.stdout.flush()
            self._in_stream = False

    # ------------------------------------------------------------------
    # Tool output
    # ------------------------------------------------------------------

    def on_tool_start(self, name: str, args: dict) -> None:
        self._end_stream()
        pad = content_pad()
        icon = _TOOL_ICONS.get(name, "⚙")
        summary = _arg_summary(name, args)
        console.print(
            f"{pad}[{PRIMARY}]{icon} {name}[/{PRIMARY}]"
            f"  [{DIM}]{summary}[/{DIM}]"
        )

    def on_tool_result(self, name: str, result: str) -> None:
        pad = content_pad()
        first_line = result.split("\n")[0].strip()
        if len(first_line) > 80:
            first_line = first_line[:77] + "…"
        console.print(f"{pad}  [{DIM}]{first_line}[/{DIM}]")
        console.print()

    def on_prune(self, dropped: int) -> None:
        if dropped > 0:
            pad = content_pad()
            console.print(
                f"{pad}[{DIM}][context: {dropped} messages pruned to free space][/{DIM}]"
            )

    def on_error(self, msg: str) -> None:
        self._end_stream()
        pad = content_pad()
        console.print(f"{pad}[{WARNING}]{msg}[/{WARNING}]")

    # ------------------------------------------------------------------
    # Approval
    # ------------------------------------------------------------------

    async def ask_approval(self, name: str, args: dict, preview: str) -> bool:
        """Show a diff/preview and prompt the user to approve or reject."""
        pad = content_pad()

        # Show preview
        if preview and preview not in ("(no changes)",):
            if name == "write_file" and ("\n+++ " in preview or "\n--- " in preview or "(new file)" in preview):
                _print_diff(preview)
            else:
                # Command or short preview
                console.print(f"{pad}  [{DIM}]{preview[:200]}[/{DIM}]")

        # Prompt
        prompt_str = f"{pad}  [{WARNING}]Approve {name}?[/{WARNING}] [y/N]: "
        console.print(prompt_str, end="")
        try:
            answer = await asyncio.to_thread(_blocking_input)
        except (EOFError, KeyboardInterrupt):
            console.print()
            return False

        approved = answer.strip().lower() in ("y", "yes")
        if approved:
            console.print(f"{pad}  [{SUCCESS}]✓ approved[/{SUCCESS}]")
        else:
            console.print(f"{pad}  [{DIM}]skipped[/{DIM}]")
        console.print()
        return approved

    # ------------------------------------------------------------------
    # Build AgentCallbacks wired to this UI
    # ------------------------------------------------------------------

    def make_callbacks(self) -> AgentCallbacks:
        return AgentCallbacks(
            on_text_token=self.on_text_token,
            on_tool_start=self.on_tool_start,
            on_tool_result=self.on_tool_result,
            on_prune=self.on_prune,
            on_error=self.on_error,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _blocking_input() -> str:
    """Read one line from stdin — runs in a thread pool from asyncio.to_thread."""
    try:
        return sys.stdin.readline().rstrip("\n")
    except EOFError:
        return ""


def _print_diff(diff_text: str) -> None:
    pad = content_pad()
    try:
        syntax = Syntax(
            diff_text,
            "diff",
            theme="monokai",
            line_numbers=False,
            word_wrap=True,
        )
        console.print(f"{pad}", end="")
        console.print(syntax)
    except Exception:
        # Fallback: plain text
        for line in diff_text.splitlines()[:30]:
            console.print(f"{pad}  {line}")
