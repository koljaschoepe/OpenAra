"""Agent command — `/agent` and shortcut `a`.

Usage in TUI:
    a                            → prompt for task, then run multi-turn session
    a fix the login bug          → start session with task immediately
    /agent config                → show agent configuration
    /agent config model <name>   → set LLM model
    /agent config url <url>      → set Ollama base URL
    /agent config reset          → restore defaults

The agent runs in a blocking asyncio loop so the TUI pauses while the
agent works. After each task the user can give a follow-up or press Enter
to exit the session. Ctrl+C ends the session at any point.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from arasul_tui.agent.agent import AgentSession
from arasul_tui.agent.config import AgentConfig, _DEFAULTS, load_agent_config, save_agent_config
from arasul_tui.agent.llm import check_connection
from arasul_tui.agent.ui.chat import ChatUI
from arasul_tui.core.state import TuiState
from arasul_tui.core.theme import DIM, ERROR, PRIMARY, SUCCESS, WARNING
from arasul_tui.core.types import CommandResult
from arasul_tui.core.ui import console, content_pad, print_info, print_warning

# ---------------------------------------------------------------------------
# Review system prompt — overrides the normal coding-agent system
# ---------------------------------------------------------------------------

_REVIEW_SYSTEM = """\
You are Open Ara, a senior code reviewer. The user has provided a git diff for review.

Give a structured review. Use these sections (omit any with no issues):
## Bugs
## Security
## Performance
## Tests
## Style

Per issue: file name, approximate line, what's wrong, how to fix it.
Be concise — don't repeat what the diff already shows.
If the diff is clean and well-tested, say so briefly.
You may call read_file to get more context around changed lines."""

_MAX_REVIEW_DIFF_CHARS = 20_000  # ≈ 5000 tokens

# ---------------------------------------------------------------------------
# Commit + Explain system prompts
# ---------------------------------------------------------------------------

_COMMIT_SYSTEM = """\
You are a git commit message writer. Given a staged diff, write a conventional commit message.

Format:
  type(scope): brief description    ← max 72 chars; scope is optional

  Optional body explaining WHY in 1-3 sentences. Skip if the subject line
  is already self-evident from the diff.

Allowed types: feat · fix · refactor · test · docs · style · chore · perf
Scope: the component or area affected (e.g. auth, api, ui, parser) — keep short.

Output ONLY the commit message text. No markdown, no quotes, no explanation."""

_MAX_COMMIT_DIFF_CHARS = 16_000

_EXPLAIN_SYSTEM = """\
You are Open Ara, a code explainer. Your job is to explain code clearly.

- Explain WHAT and WHY, not how (the code already shows how).
- Use plain language; be technical where precision matters.
- Call read_file to inspect any file mentioned or implied by the request.
- Keep explanations structured: purpose → design decisions → key components.
- No code blocks unless the user explicitly asks for a code example."""


def cmd_agent(state: TuiState, args: list[str]) -> CommandResult:
    """Start an interactive multi-turn agent session on the active project."""
    # --- subcommands ---
    if args and args[0] == "config":
        return _cmd_agent_config(args[1:])
    if args and args[0] == "undo":
        return _cmd_agent_undo(state, args[1:])
    if args and args[0] == "check":
        return _cmd_agent_check()
    if args and args[0] == "review":
        return cmd_review(state, args[1:])
    if args and args[0] == "commit":
        return cmd_commit(state, args[1:])
    if args and args[0] == "explain":
        return cmd_explain(state, args[1:])

    if not state.active_project:
        print_warning("No active project.")
        print_info("Open a project first — type its name or number.")
        return CommandResult(ok=False, style="silent")

    if args:
        task = " ".join(args).strip()
        if task:
            _run_session(task, state.active_project)
            return CommandResult(ok=True, style="silent")

    # No task provided → ask via pending_handler
    return CommandResult(
        ok=True,
        style="silent",
        prompt="Task",
        pending_handler=_agent_task_handler,
    )


def _agent_task_handler(state: TuiState, user_input: str) -> CommandResult:
    task = user_input.strip()
    if not task:
        print_info("No task provided.")
        return CommandResult(ok=True, style="silent")
    if not state.active_project:
        print_warning("Active project disappeared — please re-open.")
        return CommandResult(ok=False, style="silent")
    _run_session(task, state.active_project)
    return CommandResult(ok=True, style="silent", refresh=True)


def _run_session(task: str, project_path: Path) -> None:
    """Run a multi-turn agent session synchronously (blocks the TUI loop)."""
    ui = ChatUI(project_path)
    cfg = load_agent_config()
    ui.print_header(task)
    try:
        asyncio.run(_multi_turn_loop(task, project_path, cfg, ui))
    except KeyboardInterrupt:
        console.print()
        pad = content_pad()
        console.print(f"{pad}[{DIM}]Session ended.[/{DIM}]")


async def _multi_turn_loop(
    first_task: str,
    project_path: Path,
    cfg: AgentConfig,
    ui: ChatUI,
) -> None:
    """Async loop: run the first task, then prompt for follow-ups until Enter."""
    session = AgentSession(
        project_path,
        config=cfg,
        callbacks=ui.make_callbacks(),
        approval=ui.ask_approval,
    )

    current_task = first_task
    while True:
        result = await session.run(current_task)
        ui.print_footer(result)

        next_task = await ui.ask_next_task()
        if next_task is None:
            break
        ui.print_separator(next_task)
        current_task = next_task


# ---------------------------------------------------------------------------
# /agent config
# ---------------------------------------------------------------------------

_CONFIG_HELP = (
    "Usage: agent config [show | model <name> | url <url> | num-ctx <n> | think on/off | reset]"
)


def _cmd_agent_config(args: list[str]) -> CommandResult:
    cfg = load_agent_config()
    pad = content_pad()

    sub = args[0].lower() if args else "show"

    if sub == "show":
        think_label = "on (full reasoning)" if cfg.think else "off  (/no_think — faster)"
        console.print()
        console.print(f"{pad}[{PRIMARY}]◆ Agent Config[/{PRIMARY}]")
        console.print(f"{pad}  Model    [{DIM}]{cfg.model}[/{DIM}]")
        console.print(f"{pad}  URL      [{DIM}]{cfg.base_url}[/{DIM}]")
        console.print(f"{pad}  Context  [{DIM}]{cfg.context_limit} tokens (num_ctx: {cfg.num_ctx})[/{DIM}]")
        console.print(f"{pad}  Temp     [{DIM}]{cfg.temperature}[/{DIM}]")
        console.print(f"{pad}  Think    [{DIM}]{think_label}[/{DIM}]")
        console.print()
        return CommandResult(ok=True, style="silent")

    if sub == "model" and len(args) >= 2:
        cfg.model = args[1]
        save_agent_config(cfg)
        console.print(f"{pad}[{SUCCESS}]✓[/{SUCCESS}] Model → [{DIM}]{cfg.model}[/{DIM}]")
        return CommandResult(ok=True, style="silent")

    if sub in ("url", "base-url") and len(args) >= 2:
        cfg.base_url = args[1]
        save_agent_config(cfg)
        console.print(f"{pad}[{SUCCESS}]✓[/{SUCCESS}] URL → [{DIM}]{cfg.base_url}[/{DIM}]")
        return CommandResult(ok=True, style="silent")

    if sub == "think" and len(args) >= 2:
        val = args[1].lower() in ("on", "true", "1", "yes")
        cfg.think = val
        save_agent_config(cfg)
        label = "on (full reasoning)" if val else "off (/no_think — faster)"
        console.print(f"{pad}[{SUCCESS}]✓[/{SUCCESS}] Think → [{DIM}]{label}[/{DIM}]")
        return CommandResult(ok=True, style="silent")

    if sub in ("num-ctx", "numctx", "ctx") and len(args) >= 2:
        try:
            cfg.num_ctx = int(args[1])
        except ValueError:
            print_warning(f"num-ctx must be an integer, got: {args[1]!r}")
            return CommandResult(ok=False, style="silent")
        save_agent_config(cfg)
        console.print(f"{pad}[{SUCCESS}]✓[/{SUCCESS}] num_ctx → [{DIM}]{cfg.num_ctx}[/{DIM}]")
        return CommandResult(ok=True, style="silent")

    if sub == "reset":
        defaults = _DEFAULTS
        cfg = AgentConfig(
            base_url=defaults["base_url"],
            model=defaults["model"],
            context_limit=defaults["context_limit"],
            num_ctx=defaults["num_ctx"],
            temperature=defaults["temperature"],
            max_output_tokens=defaults["max_output_tokens"],
            safe_command_prefixes=list(defaults["safe_command_prefixes"]),
        )
        save_agent_config(cfg)
        console.print(f"{pad}[{SUCCESS}]✓[/{SUCCESS}] Config reset to defaults.")
        return CommandResult(ok=True, style="silent")

    print_warning(f"Unknown option: {sub!r}")
    print_info(_CONFIG_HELP)
    return CommandResult(ok=False, style="silent")


# ---------------------------------------------------------------------------
# /agent undo
# ---------------------------------------------------------------------------

def _cmd_agent_undo(state: TuiState, args: list[str]) -> CommandResult:
    """Restore a file from its last .openara-backups/ snapshot."""
    import asyncio

    from arasul_tui.agent.tools.file_tools import _BACKUP_DIR, undo_file

    if not state.active_project:
        print_warning("No active project.")
        return CommandResult(ok=False, style="silent")

    project_path = state.active_project
    pad = content_pad()

    if args:
        # undo a specific file
        path = args[0]
        try:
            msg = asyncio.run(undo_file(path, project_path))
            console.print(f"{pad}[{SUCCESS}]✓[/{SUCCESS}] {msg}")
        except Exception as exc:
            print_warning(str(exc))
            return CommandResult(ok=False, style="silent")
        return CommandResult(ok=True, style="silent")

    # No path: list available backups
    backup_root = project_path / _BACKUP_DIR
    if not backup_root.exists():
        print_info("No backups yet — write_file creates backups automatically.")
        return CommandResult(ok=True, style="silent")

    console.print()
    console.print(f"{pad}[{PRIMARY}]◆ Available backups[/{PRIMARY}]  [{DIM}](agent undo <path> to restore)[/{DIM}]")
    found = False
    for backup_dir in sorted(backup_root.rglob("*.bak")):
        rel = backup_dir.relative_to(backup_root)
        file_path = str(rel.parent)  # drop the timestamp filename
        import time as _time
        try:
            ts = int(backup_dir.stem) / 1000
            age = _time.time() - ts
            if age < 60:
                age_str = f"{int(age)}s ago"
            elif age < 3600:
                age_str = f"{int(age/60)}m ago"
            else:
                age_str = f"{int(age/3600)}h ago"
        except ValueError:
            age_str = ""
        console.print(f"{pad}  [{DIM}]{file_path}[/{DIM}]  {age_str}")
        found = True
    if not found:
        print_info("No backup files found.")
    console.print()
    return CommandResult(ok=True, style="silent")


# ---------------------------------------------------------------------------
# /agent check — connection health
# ---------------------------------------------------------------------------

def _cmd_agent_check() -> CommandResult:
    """Test Ollama connectivity and list available models."""
    cfg = load_agent_config()
    pad = content_pad()

    console.print()
    console.print(f"{pad}[{PRIMARY}]◆ Connection Check[/{PRIMARY}]")
    console.print(f"{pad}  URL     [{DIM}]{cfg.base_url}[/{DIM}]")
    console.print(f"{pad}  Model   [{DIM}]{cfg.model}[/{DIM}]")

    try:
        result = asyncio.run(check_connection(cfg.base_url))
    except Exception as exc:
        console.print(f"{pad}  [{ERROR}]✗  {exc}[/{ERROR}]")
        console.print()
        return CommandResult(ok=False, style="silent")

    if result["ok"]:
        console.print(f"{pad}  [{SUCCESS}]✓  Connected[/{SUCCESS}]  [{DIM}]{result['latency_ms']}ms[/{DIM}]")
        models = result.get("models", [])
        if models:
            models_str = "  ·  ".join(models[:8])
            console.print(f"{pad}  Models  [{DIM}]{models_str}[/{DIM}]")
            available = cfg.model in models
            icon = f"[{SUCCESS}]✓[/{SUCCESS}]" if available else f"[{WARNING}]![/{WARNING}]"
            status = "available" if available else "NOT FOUND — run: agent config model <name>"
            console.print(f"{pad}  Active  {icon}  [{DIM}]{cfg.model} — {status}[/{DIM}]")
    else:
        error = result.get("error", "unknown error")
        console.print(f"{pad}  [{ERROR}]✗  {error}[/{ERROR}]")
        console.print(f"{pad}  [{DIM}]Tip: agent config url http://yourserver:11434/v1[/{DIM}]")

    console.print()
    return CommandResult(ok=result["ok"], style="silent")


# ---------------------------------------------------------------------------
# /review — code review of git diff
# ---------------------------------------------------------------------------

def cmd_review(state: TuiState, args: list[str]) -> CommandResult:
    """AI code review of git changes in the active project.

    Usage:
        review              → review uncommitted changes (staged + unstaged)
        review HEAD~1       → review changes since last commit
        review main         → review changes vs main branch
    """
    if not state.active_project:
        print_warning("No active project.")
        print_info("Open a project first.")
        return CommandResult(ok=False, style="silent")

    project_path = state.active_project
    ref = args[0] if args else None

    diff, truncated = _get_git_diff(project_path, ref)
    if diff is None:
        print_info("No git repository in project directory.")
        return CommandResult(ok=True, style="silent")
    if not diff:
        print_info("Nothing to review — working tree is clean and nothing is staged.")
        return CommandResult(ok=True, style="silent")

    cfg = load_agent_config()
    ui = ChatUI(project_path)

    label = f"vs {ref}" if ref else "uncommitted changes"
    if truncated:
        label += f"  (diff truncated to {_MAX_REVIEW_DIFF_CHARS // 1000}k chars)"
    ui.print_header(f"Code Review — {label}")

    if truncated:
        pad = content_pad()
        console.print(f"{pad}[{WARNING}]⚠  Diff is large; only the first {_MAX_REVIEW_DIFF_CHARS // 1000}k chars are shown.[/{WARNING}]")
        console.print()

    try:
        asyncio.run(_run_review_async(diff, project_path, cfg, ui))
    except KeyboardInterrupt:
        console.print()
        pad = content_pad()
        console.print(f"{pad}[{DIM}]Review interrupted.[/{DIM}]")

    return CommandResult(ok=True, style="silent")


async def _run_review_async(
    diff: str,
    project_path: Path,
    cfg: AgentConfig,
    ui: ChatUI,
) -> None:
    session = AgentSession(
        project_path,
        config=cfg,
        callbacks=ui.make_callbacks(),
        approval=ui.ask_approval,
        system_override=_REVIEW_SYSTEM,
    )
    task = f"Review this diff:\n\n```diff\n{diff}\n```"
    result = await session.run(task)
    ui.print_footer(result)


def _get_staged_diff(project_path: Path) -> tuple[str | None, bool]:
    """Return (staged_diff, was_truncated). Returns (None, False) if not a git repo."""
    import subprocess

    if not (project_path / ".git").is_dir():
        return None, False

    try:
        r = subprocess.run(
            ["git", "diff", "--staged"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        diff = r.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        return "", False

    if not diff:
        return "", False

    truncated = len(diff) > _MAX_COMMIT_DIFF_CHARS
    return diff[:_MAX_COMMIT_DIFF_CHARS], truncated


# ---------------------------------------------------------------------------
# /commit — AI-generated commit message
# ---------------------------------------------------------------------------

def cmd_commit(state: TuiState, args: list[str]) -> CommandResult:
    """Generate a conventional commit message via AI and commit staged changes.

    Usage:
        commit          → analyse staged diff, propose message, ask for approval
        agent commit    → same, as agent subcommand
    """
    if not state.active_project:
        print_warning("No active project.")
        return CommandResult(ok=False, style="silent")

    project_path = state.active_project
    staged_diff, truncated = _get_staged_diff(project_path)

    if staged_diff is None:
        print_info("Not a git repository.")
        return CommandResult(ok=True, style="silent")
    if not staged_diff:
        print_info("Nothing staged. Run 'git add <files>' first.")
        return CommandResult(ok=True, style="silent")

    cfg = load_agent_config()
    ui = ChatUI(project_path)
    ui.print_header("Generate commit message")

    if truncated:
        pad = content_pad()
        console.print(f"{pad}[{WARNING}]⚠  Diff truncated to {_MAX_COMMIT_DIFF_CHARS // 1000}k chars.[/{WARNING}]")
        console.print()

    try:
        asyncio.run(_commit_flow_async(staged_diff, project_path, cfg, ui))
    except KeyboardInterrupt:
        console.print()
        pad = content_pad()
        console.print(f"{pad}[{DIM}]Commit cancelled.[/{DIM}]")

    return CommandResult(ok=True, style="silent")


async def _commit_flow_async(
    staged_diff: str,
    project_path: Path,
    cfg: AgentConfig,
    ui: ChatUI,
) -> None:
    pad = content_pad()
    session = AgentSession(
        project_path,
        config=cfg,
        callbacks=ui.make_callbacks(),
        system_override=_COMMIT_SYSTEM,
        tools_override=[],  # no tools — pure text generation
    )
    task = f"Write a commit message for this staged diff:\n\n```diff\n{staged_diff}\n```"
    result = await session.run(task)

    msg = result.text.strip() if result.text else ""
    if not msg:
        console.print(f"{pad}[{ERROR}]✗  Agent did not generate a commit message.[/{ERROR}]")
        console.print()
        return

    final_msg = await _ask_commit_approval(msg)
    if final_msg is None:
        console.print(f"{pad}[{DIM}]Commit cancelled.[/{DIM}]")
        console.print()
        return

    ok, output = _do_git_commit(project_path, final_msg)
    console.print()
    if ok:
        for line in output.splitlines():
            console.print(f"{pad}[{SUCCESS}]✓[/{SUCCESS}]  [{DIM}]{line}[/{DIM}]")
    else:
        console.print(f"{pad}[{ERROR}]✗  Commit failed:[/{ERROR}]")
        for line in output.splitlines():
            console.print(f"{pad}  [{DIM}]{line}[/{DIM}]")
    console.print()


async def _ask_commit_approval(msg: str) -> str | None:
    """Display commit message and return approved/edited message, or None to cancel."""
    pad = content_pad()
    lines = msg.splitlines()

    console.print()
    console.print(f"{pad}[{DIM}]{'─' * 56}[/{DIM}]")
    for i, line in enumerate(lines):
        if i == 0 and line:
            console.print(f"{pad}  [{PRIMARY}]{line}[/{PRIMARY}]")
        else:
            console.print(f"{pad}  [{DIM}]{line}[/{DIM}]")
    console.print(f"{pad}[{DIM}]{'─' * 56}[/{DIM}]")
    console.print()
    console.print(
        f"{pad}  [{WARNING}]Commit with this message?[/{WARNING}]"
        f" [{DIM}]y[es] · e[dit] · N[o][/{DIM}]: ",
        end="",
    )

    try:
        answer = await asyncio.to_thread(_read_stdin_line)
    except (EOFError, KeyboardInterrupt):
        console.print()
        return None

    key = answer.strip().lower()
    if key in ("y", "yes"):
        return msg
    if key in ("e", "edit"):
        console.print()
        console.print(f"{pad}  New message [{DIM}](single line; empty = keep original)[/{DIM}]:")
        console.print(f"{pad}  > ", end="")
        try:
            new_msg = await asyncio.to_thread(_read_stdin_line)
        except (EOFError, KeyboardInterrupt):
            console.print()
            return msg
        return new_msg.strip() or msg
    return None


def _read_stdin_line() -> str:
    import sys
    try:
        return sys.stdin.readline().rstrip("\n")
    except EOFError:
        return ""


def _do_git_commit(project_path: Path, message: str) -> tuple[bool, str]:
    import subprocess
    try:
        r = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, str(exc)


# ---------------------------------------------------------------------------
# /explain — explain a file, directory, or project architecture
# ---------------------------------------------------------------------------

def cmd_explain(state: TuiState, args: list[str]) -> CommandResult:
    """Explain a file, directory, or the overall project architecture.

    Usage:
        explain                 → project overview: purpose, architecture, key components
        explain auth.py         → what this file does and why
        explain src/api/        → explain the module
    """
    if not state.active_project:
        print_warning("No active project.")
        return CommandResult(ok=False, style="silent")

    project_path = state.active_project
    target = " ".join(args).strip() if args else ""
    label = target or "project architecture"
    if target:
        task = f"Explain {target}"
    else:
        task = "Give me an overview of this project — its purpose, architecture, and key components."

    cfg = load_agent_config()
    ui = ChatUI(project_path)
    ui.print_header(f"Explain: {label}")

    try:
        asyncio.run(_run_explain_async(task, project_path, cfg, ui))
    except KeyboardInterrupt:
        console.print()
        pad = content_pad()
        console.print(f"{pad}[{DIM}]Interrupted.[/{DIM}]")

    return CommandResult(ok=True, style="silent")


async def _run_explain_async(task: str, project_path: Path, cfg: AgentConfig, ui: ChatUI) -> None:
    session = AgentSession(
        project_path,
        config=cfg,
        callbacks=ui.make_callbacks(),
        approval=ui.ask_approval,
        system_override=_EXPLAIN_SYSTEM,
    )
    result = await session.run(task)
    ui.print_footer(result)


def _get_git_diff(project_path: Path, ref: str | None = None) -> tuple[str | None, bool]:
    """Return (diff_text, was_truncated). Returns (None, False) if not a git repo."""
    import subprocess

    if not (project_path / ".git").is_dir():
        return None, False

    def _git(*cmd: str) -> str:
        try:
            r = subprocess.run(
                ["git", *cmd],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            return r.stdout.strip()
        except (subprocess.TimeoutExpired, OSError):
            return ""

    if ref:
        diff = _git("diff", ref)
    else:
        diff = _git("diff", "--staged") or _git("diff")

    if not diff:
        return "", False

    truncated = len(diff) > _MAX_REVIEW_DIFF_CHARS
    return diff[:_MAX_REVIEW_DIFF_CHARS], truncated
