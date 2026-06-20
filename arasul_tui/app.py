from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style

from arasul_tui.agent.agent import AgentSession
from arasul_tui.agent.config import AgentConfig, load_agent_config
from arasul_tui.agent.ui.chat import ChatUI
from arasul_tui.core.auth import get_auth_env, is_claude_configured
from arasul_tui.core.router import REGISTRY, run_command
from arasul_tui.core.state import Screen, TuiState
from arasul_tui.core.theme import DIM, PRIMARY, SUCCESS, WARNING
from arasul_tui.core.types import PendingHandler
from arasul_tui.core.ui import (
    VERSION,
    build_prompt,
    console,
    content_pad,
    print_error,
    print_header,
    print_info,
    print_result,
    print_separator,
    print_warning,
    project_list,
)


# ---------------------------------------------------------------------------
# CLI arg parsing
# ---------------------------------------------------------------------------

@dataclass
class _CliArgs:
    initial_task: str | None = None
    continue_flag: bool = False
    model_override: str | None = None
    project_override: Path | None = None
    help_flag: bool = False
    version_flag: bool = False


def _parse_cli_args(argv: list[str]) -> _CliArgs:
    result = _CliArgs()
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("-c", "--continue"):
            result.continue_flag = True
        elif arg in ("-m", "--model") and i + 1 < len(argv):
            result.model_override = argv[i + 1]
            i += 1
        elif arg in ("-p", "--project") and i + 1 < len(argv):
            result.project_override = Path(argv[i + 1]).expanduser().resolve()
            i += 1
        elif arg in ("-h", "--help"):
            result.help_flag = True
        elif arg in ("-v", "--version"):
            result.version_flag = True
        elif not arg.startswith("-"):
            result.initial_task = " ".join(argv[i:])
            break
        i += 1
    return result


def _print_help() -> None:
    print(f"""  Open Ara — local AI coding assistant

  Usage: ara [task] [options]

  Options:
    -c, --continue        Resume last session in current directory
    -m, --model <name>    Override model for this session
    -p, --project <path>  Use this project directory (default: git root / cwd)
    -v, --version         Show version
    -h, --help            Show this help

  In the REPL:
    <task>                Send a task to the agent
    #<fact>               Save a note to ARA.md (e.g. #auth uses JWT RS256)
    !<cmd>                Run a shell command directly (e.g. !git status)
    /help                 All slash commands
    /review [ref]         AI code review of git changes
    /commit               Generate a commit message for staged changes
    /explain [target]     Explain a file or the project architecture
    /new                  Clear the conversation (fresh session)
    /agent config         Show/change model and server URL
    /exit                 Quit  (also: Ctrl+D)

  Examples:
    ara                              Interactive session in current directory
    ara "fix the login bug"          Start immediately with a task
    ara --continue                   Resume last conversation
    ara --model qwen3:14b-nothink    Fast mode (no reasoning)
""")


# ---------------------------------------------------------------------------
# Project / session helpers
# ---------------------------------------------------------------------------

def _find_git_root(path: Path) -> Path:
    """Walk up directory tree to find the git root, or return path if not in a repo."""
    current = path.resolve()
    while current != current.parent:
        if (current / ".git").is_dir():
            return current
        current = current.parent
    return path.resolve()


def _session_file(project_path: Path) -> Path:
    h = hashlib.md5(str(project_path).encode()).hexdigest()[:8]
    return Path.home() / ".config" / "arasul" / "sessions" / f"{h}.json"


def _save_session(project_path: Path, messages: list[dict]) -> None:
    if not messages:
        return
    sf = _session_file(project_path)
    with contextlib.suppress(OSError):
        sf.parent.mkdir(parents=True, exist_ok=True)
        sf.write_text(json.dumps(messages, ensure_ascii=False), encoding="utf-8")


def _load_session(project_path: Path) -> list[dict]:
    sf = _session_file(project_path)
    try:
        data = json.loads(sf.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _make_agent_session(
    project_path: Path,
    cfg: AgentConfig,
    initial_messages: list[dict] | None = None,
) -> tuple[AgentSession, ChatUI]:
    ui = ChatUI(project_path)
    session = AgentSession(
        project_path,
        config=cfg,
        callbacks=ui.make_callbacks(),
        approval=ui.ask_approval,
        initial_messages=initial_messages,
    )
    return session, ui


def _run_task_in_session(task: str, agent_session: AgentSession, ui: ChatUI) -> None:
    """Run one task on a persistent session — no inner follow-up loop."""
    ui.print_header(task)
    try:
        result = asyncio.run(agent_session.run(task))
        ui.print_footer(result)
    except KeyboardInterrupt:
        pad = content_pad()
        console.print()
        console.print(f"{pad}[{DIM}]Interrupted.[/{DIM}]")


# ---------------------------------------------------------------------------
# ARA.md helpers
# ---------------------------------------------------------------------------

def _append_to_ara_md(fact: str, project_path: Path) -> None:
    """Append a fact line to <project>/ARA.md — creates the file if absent."""
    ara = project_path / "ARA.md"
    try:
        if not ara.exists():
            ara.write_text(
                f"# {project_path.name}\n\n## Notes\n\n- {fact}\n",
                encoding="utf-8",
            )
        else:
            with ara.open("a", encoding="utf-8") as fh:
                fh.write(f"- {fact}\n")
        pad = content_pad()
        console.print(f"{pad}[{DIM}]Saved to ARA.md[/{DIM}]")
    except OSError as exc:
        print_error(f"Could not write ARA.md: {exc}")


async def _do_compact(session: "AgentSession", cfg: AgentConfig) -> None:
    """Summarise conversation history and replace it with a compact form."""
    from arasul_tui.agent.llm import LLMError, chat

    if not session.messages:
        return

    # Build a short transcript (last 40 turns)
    parts: list[str] = []
    for m in session.messages[-40:]:
        role = m.get("role", "")
        content = m.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                b.get("text", "")
                for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            )
        if content:
            parts.append(f"{role.upper()}: {str(content)[:600]}")

    transcript = "\n".join(parts)
    prompt = (
        "Create a concise briefing of this conversation for a fresh agent taking over. "
        "Include: what was accomplished, key decisions, current code state, what the user wants next.\n\n"
        + transcript
    )

    try:
        response = await chat(
            messages=[{"role": "user", "content": prompt}],
            system="You create concise conversation summaries.",
            tools=[],
            config=cfg,
            on_token=None,
        )
        summary = response.text if response else "(summary unavailable)"
    except (LLMError, Exception):
        summary = "(summary unavailable — conversation truncated)"

    session.messages = [
        {"role": "user", "content": f"[Compact context]\n{summary}"},
        {"role": "assistant", "content": "Understood. Continuing from the summary above."},
    ]


# ---------------------------------------------------------------------------
# Shell passthrough
# ---------------------------------------------------------------------------

def _run_shell_command(cmd: str, cwd: Path) -> None:
    """Execute a shell command directly (streams output via inherited stdio)."""
    pad = content_pad()
    try:
        proc = subprocess.run(cmd, shell=True, cwd=cwd)
        if proc.returncode != 0:
            console.print(f"{pad}[{WARNING}]Exit {proc.returncode}[/{WARNING}]")
    except OSError as exc:
        print_error(str(exc))


# ---------------------------------------------------------------------------
# Compact startup header
# ---------------------------------------------------------------------------

def _print_coding_header(project_path: Path, cfg: AgentConfig) -> None:
    """Minimal coding-assistant header: project, model, server, git branch."""
    from rich.markup import escape as _esc

    pad = content_pad()
    console.print()
    console.print(
        f"{pad}[bold {PRIMARY}]◆[/bold {PRIMARY}]  [bold]Open Ara[/bold]  [{DIM}]{VERSION}[/{DIM}]",
        highlight=False,
    )
    name = _esc(project_path.name)
    model = _esc(cfg.model)
    url = _esc(cfg.base_url)
    console.print(
        f"{pad}   [{PRIMARY}]{name}[/{PRIMARY}]  [{DIM}]{model}  ·  {url}[/{DIM}]",
        highlight=False,
    )

    # Git branch (best-effort, no crash)
    try:
        br = subprocess.run(
            ["git", "symbolic-ref", "--short", "HEAD"],
            cwd=project_path, capture_output=True, text=True, timeout=3,
        )
        dr = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=project_path, capture_output=True, text=True, timeout=3,
        )
        branch = br.stdout.strip()
        if branch:
            dirty_mark = f"  [{WARNING}]*[/{WARNING}]" if dr.stdout.strip() else ""
            console.print(
                f"{pad}   [{DIM}]{_esc(branch)}{dirty_mark}[/{DIM}]",
                highlight=False,
            )
    except Exception:
        pass

    console.print(
        f"{pad}   [{DIM}]Type a task · #fact saves to ARA.md · /help for commands · Ctrl+D to exit[/{DIM}]",
        highlight=False,
    )
    console.print()


# ---------------------------------------------------------------------------
# Command helpers (unchanged from original)
# ---------------------------------------------------------------------------

def _suggest_alternatives(command: str) -> None:
    """Show helpful suggestions when a command isn't recognized."""
    q = command.lower()
    suggestions: list[str] = []

    for spec in REGISTRY.specs():
        name = spec.name
        if len(q) >= 3 and (q in name or name in q):
            suggestions.append(name)
            continue
        common = 0
        for a, b in zip(q, name, strict=False):
            if a == b:
                common += 1
            else:
                break
        if common >= 2 and len(q) <= len(name) + 2:
            suggestions.append(name)
            continue
        for alias in spec.aliases:
            if q in alias or alias in q:
                suggestions.append(name)
                break

    if suggestions:
        unique = list(dict.fromkeys(suggestions))[:3]
        hint = ", ".join(f"[bold]{s}[/bold]" for s in unique)
        print_warning(f"I don't know '[bold]{command}[/bold]'. Did you mean: {hint}?")
    else:
        print_warning(f"Unknown: '[bold]{command}[/bold]'. Type /help for commands.")


class SmartCompleter(Completer):
    """Completer that works with both slash commands and natural language."""

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor.lstrip()
        if not text:
            for spec in REGISTRY.specs():
                yield Completion(
                    spec.name,
                    start_position=0,
                    display=HTML(f"<b>{spec.name}</b>"),
                    display_meta=spec.help_text,
                )
            return

        if text.startswith("/"):
            yield from self._slash_completions(text)
            return

        yield from self._natural_completions(text)

    def _slash_completions(self, text: str):
        body = text[1:]
        parts = body.split()
        has_trailing_space = body.endswith(" ")

        if len(parts) <= 1 and not has_trailing_space:
            prefix = parts[0] if parts else ""
            for spec in REGISTRY.specs():
                if spec.name.startswith(prefix):
                    cmd_text = f"/{spec.name}"
                    yield Completion(
                        cmd_text,
                        start_position=-len(text),
                        display=HTML(f"<b>/{spec.name}</b>"),
                        display_meta=spec.help_text,
                    )
            return

        cmd = parts[0]
        spec = REGISTRY.get(cmd)
        if spec and spec.subcommands:
            pref = ""
            if len(parts) >= 2 and not has_trailing_space:
                pref = parts[1]
            for sub, desc in spec.subcommands.items():
                if sub.startswith(pref):
                    full = f"/{cmd} {sub}"
                    yield Completion(
                        full,
                        start_position=-len(text),
                        display=HTML(f"<b>/{cmd}</b> {sub}"),
                        display_meta=desc,
                    )
            return

        if cmd == "open":
            names = project_list()
            pref = ""
            if len(parts) >= 2 and not has_trailing_space:
                pref = parts[1]
            for name in names:
                if name.startswith(pref):
                    full = f"/open {name}"
                    yield Completion(
                        full,
                        start_position=-len(text),
                        display=HTML(f"<b>/open</b> {name}"),
                        display_meta="Open project",
                    )

    def _natural_completions(self, text: str):
        q = text.lower()

        for spec in REGISTRY.specs():
            if spec.name.startswith(q) or q in spec.name:
                yield Completion(
                    spec.name,
                    start_position=-len(text),
                    display=HTML(f"<b>{spec.name}</b>"),
                    display_meta=spec.help_text,
                )

        seen = set()
        for spec in REGISTRY.specs():
            for alias in spec.aliases:
                if alias.startswith(q) and alias not in seen:
                    seen.add(alias)
                    yield Completion(
                        alias,
                        start_position=-len(text),
                        display=HTML(f"{alias}"),
                        display_meta=f"{spec.help_text}",
                    )

        for name in project_list():
            if name.lower().startswith(q) or q in name.lower():
                yield Completion(
                    name,
                    start_position=-len(text),
                    display=HTML(f"<b>{name}</b>"),
                    display_meta="Open project",
                )


def _handle_number(state: TuiState, num: int) -> bool:
    projects = project_list()
    if 1 <= num <= len(projects):
        name = projects[num - 1]
        target = (state.project_root / name).resolve()
        if target.exists() and target.is_dir():
            state.active_project = target
            state.screen = Screen.PROJECT
            return True
    return False


def _fuzzy_match(query: str, projects: list[str]) -> list[str]:
    q = query.lower()
    exact = [p for p in projects if p.lower() == q]
    if exact:
        return exact
    prefix = [p for p in projects if p.lower().startswith(q)]
    if prefix:
        return prefix
    sub = [p for p in projects if q in p.lower()]
    if sub:
        return sub

    def _score(name: str) -> int:
        n = name.lower()
        idx = 0
        for ch in q:
            pos = n.find(ch, idx)
            if pos == -1:
                return -1
            idx = pos + 1
        return idx - len(q)

    scored = [(p, _score(p)) for p in projects]
    matches = [(p, s) for p, s in scored if s >= 0]
    matches.sort(key=lambda x: x[1])
    return [p for p, _ in matches]


def _try_launch_shortcut(state: TuiState, command: str) -> tuple[str, Path] | None:
    if not state.active_project:
        return None

    lower = command.lower()

    if lower in ("g", "lazygit"):
        if not shutil.which("lazygit"):
            print_error("[bold]lazygit[/bold] is not installed.")
            print_info("Install: [bold]brew install lazygit[/bold] (macOS) or [bold]sudo apt install lazygit[/bold]")
            return None
        print_info(f"Starting [bold]lazygit[/bold] in [dim]{state.active_project.name}[/dim] ...")
        return ("lazygit", state.active_project)

    if lower == "c":
        if not is_claude_configured():
            return None
        if not shutil.which("claude"):
            print_error("[bold]claude[/bold] is not installed.")
            print_info("Install: [bold]npm install -g @anthropic-ai/claude-code[/bold]")
            return None
        print_info(f"Starting [bold]Claude Code[/bold] in [dim]{state.active_project.name}[/dim] ...")
        return ("claude", state.active_project)

    return None


def _try_fuzzy_project(state: TuiState, command: str) -> bool:
    projects = project_list()
    matches = _fuzzy_match(command, projects)

    if len(matches) == 1:
        target = (state.project_root / matches[0]).resolve()
        if target.exists() and target.is_dir():
            state.active_project = target
            state.screen = Screen.PROJECT
            print_header(state, full=True)
            return True
    elif len(matches) > 1:
        print_info(f"[bold]{len(matches)}[/bold] matches for [dim]{command}[/dim]:")
        pad = content_pad()
        for i, m in enumerate(matches[:5], 1):
            console.print(f"{pad}  [cyan]{i}[/cyan]  {m}", highlight=False)
        return True

    return False


def _dispatch_command(state: TuiState, command: str) -> tuple:
    """Route to a known command. Returns (result, launch, should_break, matched).

    matched=False means nothing handled the input — caller decides what to do
    (run as agent task if a project is active, else suggest alternatives).
    """
    lower = command.lower()

    if lower == "n":
        return run_command(state, "/create"), None, False, True
    if lower == "d":
        return run_command(state, "/delete"), None, False, True

    if command.isdigit():
        num = int(command)
        if _handle_number(state, num):
            print_header(state, full=True)
        else:
            print_warning(f"No project with number [bold]{num}[/bold].")
        return None, None, False, True

    if lower in ("b", "back", "home", "main"):
        if state.active_project:
            state.active_project = None
            state.screen = Screen.MAIN
            print_header(state, full=True)
        else:
            print_info("Already at the main screen.")
        return None, None, False, True

    launch = _try_launch_shortcut(state, command)
    if launch:
        return None, launch, True, True
    if state.active_project and lower == "c" and not is_claude_configured():
        return run_command(state, "/claude"), None, False, True

    if command.startswith("/"):
        result = run_command(state, command)
        return result, None, result.quit_app, True

    if state.active_project:
        # Coding mode: exact name / alias match only.
        # Fuzzy substring matching is skipped so task descriptions like
        # "fix the login bug" don't accidentally trigger TUI commands.
        spec, args = REGISTRY.resolve_exact(command)
        if spec:
            result = spec.handler(state, args)
            return result, None, result.quit_app, True
        return None, None, False, False  # → caller runs as agent task

    # Dashboard mode (no active project): full fuzzy matching + project nav
    spec, args = REGISTRY.resolve(command)
    if spec:
        result = spec.handler(state, args)
        return result, None, result.quit_app, True

    if _try_fuzzy_project(state, command):
        return None, None, False, True

    return None, None, False, False


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def _check_direct_url(url: str) -> bool:
    """Return True if the Ollama server at `url` responds within 3 s."""
    base = url.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    try:
        with urllib.request.urlopen(base + "/api/version", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def _ensure_tunnel_if_configured(cfg: AgentConfig | None = None) -> None:
    from arasul_tui.core.tunnel import ensure_ssh_tunnel, get_install_config

    install = get_install_config()
    if install.get("connection_type") != "ssh":
        return

    ssh_host = install.get("ssh_host", "")
    ollama_host = install.get("ollama_host", "localhost")
    ollama_port = int(install.get("ollama_port", 11434))

    if not ssh_host:
        return

    ok, msg = ensure_ssh_tunnel(ssh_host, ollama_host, ollama_port)
    pad = content_pad()
    if ok:
        console.print(f"{pad}[{DIM}]⟳  {msg}[/{DIM}]")
    else:
        # Tunnel failed — check if the server URL is directly reachable
        direct_ok = cfg and _check_direct_url(cfg.base_url)
        if direct_ok:
            console.print(
                f"{pad}[{WARNING}]⚠  SSH tunnel failed ({msg})[/{WARNING}]"
                f" — [{SUCCESS}]direct connection works ✓[/{SUCCESS}]"
            )
            console.print(
                f"{pad}[{DIM}]   Tip: run [bold]ara setup[/bold] to switch to direct mode permanently.[/{DIM}]"
            )
        else:
            console.print(f"{pad}[{WARNING}]⚠  SSH tunnel failed: {msg}[/{WARNING}]")
            console.print(f"{pad}[{DIM}]   Run: ara setup — to reconfigure the server URL.[/{DIM}]")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run() -> None:
    # --- CLI args ---
    cli = _parse_cli_args(sys.argv[1:])

    if cli.version_flag:
        print(f"Open Ara {VERSION}")
        return
    if cli.help_flag:
        _print_help()
        return

    # --- Determine project directory ---
    cwd = Path.cwd()
    project_path = cli.project_override or _find_git_root(cwd)

    # --- State ---
    try:
        state = TuiState(registry=REGISTRY)
        state.active_project = project_path
        state.screen = Screen.PROJECT
    except Exception as exc:
        print_error(f"Startup failed: {exc}")
        return

    # --- Config ---
    cfg = load_agent_config()
    if cli.model_override:
        cfg.model = cli.model_override

    # --- SSH tunnel (with direct-URL fallback) ---
    _ensure_tunnel_if_configured(cfg)

    # --- Session continuity ---
    initial_messages: list[dict] | None = None
    if cli.continue_flag:
        loaded = _load_session(project_path)
        if loaded:
            initial_messages = loaded
        else:
            pad = content_pad()
            console.print(f"{pad}[{DIM}]No saved session found for this directory.[/{DIM}]")

    # --- Persistent agent session (lives for the whole ara invocation) ---
    agent_session, ui = _make_agent_session(project_path, cfg, initial_messages)
    agent_project = project_path

    # --- Prompt session (prompt_toolkit) ---
    history_path = Path.home() / ".config" / "arasul" / "history"
    with contextlib.suppress(OSError):
        history_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        prompt_session: PromptSession[str] = PromptSession(
            history=FileHistory(str(history_path)),
            completer=SmartCompleter(),
            complete_while_typing=True,
            style=Style.from_dict(
                {
                    "completion-menu": "bg:default",
                    "completion-menu.completion": "bg:default #888888",
                    "completion-menu.completion.current": "bg:ansicyan #000000 bold",
                    "completion-menu.meta.completion": "bg:default #555555",
                    "completion-menu.meta.completion.current": "bg:ansicyan #333333",
                    "scrollbar.background": "bg:default",
                    "scrollbar.button": "bg:default",
                }
            ),
        )
    except Exception as exc:
        print_error(f"Terminal initialization failed: {exc}")
        return

    # --- Startup display ---
    _print_coding_header(project_path, cfg)
    state.first_run = False

    if cli.continue_flag and initial_messages:
        turns = sum(1 for m in initial_messages if m.get("role") == "user")
        pad = content_pad()
        console.print(f"{pad}[{DIM}]Resumed — {turns} prior turn(s).[/{DIM}]\n")

    # --- Onboarding (first launch only) ---
    from arasul_tui.core.onboarding import mark_onboarded, needs_onboarding, show_welcome

    pending_handler: PendingHandler | None = None
    wizard_step: tuple[int, int, str] | None = None
    launch_request: tuple[str, Path] | None = None
    _in_onboarding = False

    if needs_onboarding():
        result = show_welcome()
        if result.prompt and result.pending_handler:
            _in_onboarding = True
            pending_handler = result.pending_handler
            wizard_step = result.wizard_step

    # --- Result handler (closure — can update session refs via nonlocal) ---
    def _handle_result(result) -> None:
        nonlocal pending_handler, wizard_step, launch_request
        nonlocal agent_session, ui, agent_project

        print_result(result)

        if result.prompt and result.pending_handler:
            pending_handler = result.pending_handler
            wizard_step = result.wizard_step

        if result.reset_session:
            _save_session(agent_project, agent_session.messages)
            agent_session, ui = _make_agent_session(state.active_project or project_path, cfg)
            agent_project = state.active_project or project_path
            pad = content_pad()
            console.print(f"{pad}[{DIM}]Session cleared.[/{DIM}]")
        elif result.compact_session:
            pad = content_pad()
            console.print(f"{pad}[{DIM}]Compacting context …[/{DIM}]")
            asyncio.run(_do_compact(agent_session, cfg))
            turns = sum(1 for m in agent_session.messages if m.get("role") == "user")
            console.print(f"{pad}[{DIM}]Done — context reduced to {turns} message(s).[/{DIM}]")
        elif result.refresh:
            new_project = state.active_project or project_path
            if new_project != agent_project:
                _save_session(agent_project, agent_session.messages)
                agent_session, ui = _make_agent_session(new_project, cfg)
                agent_project = new_project

        if result.launch_command and result.launch_cwd:
            launch_request = (result.launch_command, result.launch_cwd)

    # --- Run initial task from CLI (ara "fix the bug") ---
    if cli.initial_task and not _in_onboarding:
        _run_task_in_session(cli.initial_task, agent_session, ui)

    # --- Main REPL loop ---
    while True:
        try:
            print_separator()
            prompt_markup = build_prompt(state, wizard_step)
            raw = prompt_session.prompt(
                HTML(prompt_markup),
                completer=None if pending_handler else SmartCompleter(),
            )
        except EOFError:
            # Ctrl+D — clean exit
            break
        except KeyboardInterrupt:
            # Ctrl+C — interrupt but stay in loop (like Claude Code)
            console.print()
            continue
        except Exception as exc:
            print_error(f"Terminal error ({type(exc).__name__}): {exc}")
            break

        command = raw.strip()
        if not command:
            continue

        # --- Wizard / pending handler mode ---
        if pending_handler:
            if command.lower() == "q":
                pending_handler = None
                wizard_step = None
                state._wizard.clear()
                if _in_onboarding:
                    mark_onboarded()
                    _in_onboarding = False
                print_info("Cancelled.")
                continue
            try:
                result = pending_handler(state, command)
            except Exception as exc:
                pending_handler = None
                wizard_step = None
                state._wizard.clear()
                print_error(f"Command failed ({type(exc).__name__}): {exc}")
                continue
            pending_handler = None
            wizard_step = None
            if _in_onboarding and not result.prompt:
                _in_onboarding = False
            _handle_result(result)
            if result.quit_app:
                break
            continue

        # --- ARA.md fact: #note ---
        if command.startswith("#"):
            fact = command[1:].strip()
            if fact:
                _append_to_ara_md(fact, state.active_project or project_path)
            continue

        # --- Shell passthrough: !cmd ---
        if command.startswith("!"):
            _run_shell_command(command[1:].strip(), state.active_project or cwd)
            continue

        # --- Known TUI commands (slash, natural language, shortcuts) ---
        try:
            result, launch, should_break, matched = _dispatch_command(state, command)
        except Exception as exc:
            print_error(f"Command failed ({type(exc).__name__}): {exc}")
            continue

        if matched:
            if result:
                _handle_result(result)
            if launch:
                launch_request = launch
            if should_break or (result and result.quit_app):
                break
            continue

        # --- Agent fallback: anything unrecognised goes to the LLM ---
        if state.active_project:
            _run_task_in_session(command, agent_session, ui)
            continue

        # No active project and no match
        _suggest_alternatives(command)

    # --- Save session on clean exit ---
    _save_session(agent_project, agent_session.messages)

    # --- Hand off to external program (lazygit / claude) ---
    if launch_request:
        cmd, launch_cwd = launch_request
        os.environ.update(get_auth_env())
        try:
            os.chdir(str(launch_cwd))
        except OSError:
            print_warning(f"Directory not accessible: {launch_cwd}")
            return
        try:
            os.execvp(cmd, [cmd])
        except OSError as exc:
            print_error(f"Failed to launch [bold]{cmd}[/bold]: {exc}")


if __name__ == "__main__":
    run()
