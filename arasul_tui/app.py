from __future__ import annotations

import contextlib
import os
import shutil
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style

from arasul_tui.core.auth import get_auth_env, is_claude_configured
from arasul_tui.core.router import REGISTRY, run_command
from arasul_tui.core.state import Screen, TuiState
from arasul_tui.core.types import PendingHandler
from arasul_tui.core.ui import (
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


def _suggest_alternatives(command: str) -> None:
    """Show helpful suggestions when a command isn't recognized."""
    q = command.lower()
    suggestions: list[str] = []

    # Check for close matches in command names
    for spec in REGISTRY.specs():
        name = spec.name
        # Levenshtein-like: allow 1-2 char difference for short names
        if len(q) >= 3 and (q in name or name in q):
            suggestions.append(name)
            continue
        # Check prefix overlap (at least 2 chars matching)
        common = 0
        for a, b in zip(q, name, strict=False):
            if a == b:
                common += 1
            else:
                break
        if common >= 2 and len(q) <= len(name) + 2:
            suggestions.append(name)
            continue
        # Check aliases
        for alias in spec.aliases:
            if q in alias or alias in q:
                suggestions.append(name)
                break

    if suggestions:
        unique = list(dict.fromkeys(suggestions))[:3]
        hint = ", ".join(f"[bold]{s}[/bold]" for s in unique)
        print_warning(f"I don't know '[bold]{command}[/bold]'. Did you mean: {hint}?")
    else:
        print_warning(f"I don't know '[bold]{command}[/bold]'. Try [bold]help[/bold] to see what I can do.")


class SmartCompleter(Completer):
    """Completer that works with both slash commands and natural language."""

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor.lstrip()
        if not text:
            # Show all top-level commands on Tab with empty input
            for spec in REGISTRY.specs():
                yield Completion(
                    spec.name,
                    start_position=0,
                    display=HTML(f"<b>{spec.name}</b>"),
                    display_meta=spec.help_text,
                )
            return

        # Slash command mode
        if text.startswith("/"):
            yield from self._slash_completions(text)
            return

        # Natural language mode — complete command names + aliases
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

        # Subcommand completion
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

        # /open <name> completion
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

        # Command names
        for spec in REGISTRY.specs():
            if spec.name.startswith(q) or q in spec.name:
                yield Completion(
                    spec.name,
                    start_position=-len(text),
                    display=HTML(f"<b>{spec.name}</b>"),
                    display_meta=spec.help_text,
                )

        # Aliases (only if no command name matched the prefix)
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

        # Project names
        for name in project_list():
            if name.lower().startswith(q) or q in name.lower():
                yield Completion(
                    name,
                    start_position=-len(text),
                    display=HTML(f"<b>{name}</b>"),
                    display_meta="Open project",
                )


def _handle_number(state: TuiState, num: int) -> bool:
    """Select project by number. Returns True if handled."""
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
    """Simple fuzzy matching: score projects by substring and prefix match."""
    q = query.lower()
    exact = [p for p in projects if p.lower() == q]
    if exact:
        return exact
    prefix = [p for p in projects if p.lower().startswith(q)]
    if prefix:
        return prefix
    # Substring match
    sub = [p for p in projects if q in p.lower()]
    if sub:
        return sub

    # Character-by-character fuzzy
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
    """Handle g/lazygit and c/claude shortcuts. Returns (cmd, cwd) or None."""
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
            return None  # caller will dispatch to /claude
        if not shutil.which("claude"):
            print_error("[bold]claude[/bold] is not installed.")
            print_info("Install: [bold]npm install -g @anthropic-ai/claude-code[/bold]")
            return None
        print_info(f"Starting [bold]Claude Code[/bold] in [dim]{state.active_project.name}[/dim] ...")
        return ("claude", state.active_project)

    return None


def _try_fuzzy_project(state: TuiState, command: str) -> bool:
    """Try to match input to a project name. Returns True if handled."""
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
    """Dispatch a single command. Returns (result_or_none, launch_request, should_break)."""
    lower = command.lower()

    # Shortcut: n (create), d (delete)
    if lower == "n":
        return run_command(state, "/create"), None, False
    if lower == "d":
        return run_command(state, "/delete"), None, False

    # Number selection
    if command.isdigit():
        num = int(command)
        if _handle_number(state, num):
            print_header(state, full=True)
        else:
            print_warning(f"No project with number [bold]{num}[/bold].")
        return None, None, False

    # Back to main screen
    if lower in ("b", "back", "home", "main"):
        if state.active_project:
            state.active_project = None
            state.screen = Screen.MAIN
            print_header(state, full=True)
        else:
            print_info("Already at the main screen.")
        return None, None, False

    # Launch shortcuts (g/lazygit, c/claude)
    launch = _try_launch_shortcut(state, command)
    if launch:
        return None, launch, True
    # c shortcut without claude configured → run /claude wizard
    if state.active_project and lower == "c" and not is_claude_configured():
        return run_command(state, "/claude"), None, False

    # Slash commands
    if command.startswith("/"):
        result = run_command(state, command)
        return result, None, result.quit_app

    # Natural language command resolve
    spec, args = REGISTRY.resolve(command)
    if spec:
        result = spec.handler(state, args)
        return result, None, result.quit_app

    # Fuzzy project search
    if _try_fuzzy_project(state, command):
        return None, None, False

    # Nothing matched
    _suggest_alternatives(command)
    return None, None, False


def run() -> None:
    try:
        state = TuiState(registry=REGISTRY)
    except Exception as exc:
        print_error(f"Startup failed: {exc}")
        return

    pending_handler: PendingHandler | None = None
    wizard_step: tuple[int, int, str] | None = None
    launch_request: tuple[str, Path] | None = None

    history_path = Path.home() / ".config" / "arasul" / "history"
    with contextlib.suppress(OSError):
        history_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        session: PromptSession[str] = PromptSession(
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
        # Graceful fallback if prompt_toolkit can't initialize (e.g., broken TTY)
        print_error(f"Terminal initialization failed: {exc}")
        return

    print_header(state, full=True)
    state.first_run = False

    # First-launch onboarding (minimal: just ask for name if unknown)
    from arasul_tui.core.onboarding import mark_onboarded, needs_onboarding, show_welcome

    _in_onboarding = False
    if needs_onboarding():
        result = show_welcome()
        if result.prompt and result.pending_handler:
            _in_onboarding = True
            pending_handler = result.pending_handler
            wizard_step = result.wizard_step
        elif result.refresh:
            print_header(state, full=True)

    def _handle_result(result) -> None:
        nonlocal pending_handler, wizard_step, launch_request
        print_result(result)
        if result.prompt and result.pending_handler:
            pending_handler = result.pending_handler
            wizard_step = result.wizard_step
        if result.refresh:
            print_header(state, full=True)
        if result.launch_command and result.launch_cwd:
            launch_request = (result.launch_command, result.launch_cwd)

    while True:
        try:
            print_separator()
            prompt_markup = build_prompt(state, wizard_step)
            raw = session.prompt(
                HTML(prompt_markup),
                completer=None if pending_handler else SmartCompleter(),
            )
        except (EOFError, KeyboardInterrupt):
            break
        except Exception as exc:
            # Connection lost or terminal issue — log and exit gracefully
            print_error(f"Terminal error ({type(exc).__name__}): {exc}")
            break

        command = raw.strip()
        if not command:
            continue

        # Wizard mode
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

        # Normal dispatch
        try:
            result, launch, should_break = _dispatch_command(state, command)
        except Exception as exc:
            print_error(f"Command failed ({type(exc).__name__}): {exc}")
            continue
        if result:
            _handle_result(result)
        if launch:
            launch_request = launch
        if should_break or (result and result.quit_app):
            break

    if launch_request:
        cmd, cwd = launch_request
        os.environ.update(get_auth_env())
        try:
            os.chdir(str(cwd))
        except OSError:
            print_warning(f"Directory not accessible: {cwd}")
            return
        try:
            os.execvp(cmd, [cmd])
        except OSError as exc:
            print_error(f"Failed to launch [bold]{cmd}[/bold]: {exc}")
            return


if __name__ == "__main__":
    run()
