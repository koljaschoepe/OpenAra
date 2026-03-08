from __future__ import annotations

from rich import box
from rich.padding import Padding
from rich.panel import Panel
from rich.table import Table

from arasul_tui.core.registry import CommandRegistry
from arasul_tui.core.state import Screen, TuiState
from arasul_tui.core.theme import DIM, PRIMARY
from arasul_tui.core.types import CommandResult
from arasul_tui.core.ui import _adaptive_width, _frame_left_pad, console, content_pad


def _box(title: str, rows: list[str], pad: str) -> None:
    """Print a responsive rounded panel with title and content rows."""
    w = _adaptive_width() - 4
    left_pad = _frame_left_pad() + 2
    text = "\n".join(rows)
    p = Panel(
        text,
        title=f"[bold {PRIMARY}]{title}[/bold {PRIMARY}]",
        title_align="left",
        border_style="dim",
        box=box.ROUNDED,
        padding=(0, 1),
        width=w,
    )
    console.print(Padding(p, (0, 0, 0, left_pad)), highlight=False)


# ---------------------------------------------------------------------------
# /help (contextual, visual)
# ---------------------------------------------------------------------------


def _cmd_detail(name: str, pad: str, reg: CommandRegistry) -> bool:
    """Show detailed help for a single command. Returns True if found."""
    spec = reg.get(name.lower())
    if not spec:
        # Try alias
        for s in reg.specs():
            if name.lower() in [a.lower() for a in s.aliases]:
                spec = s
                break
    if not spec:
        return False

    console.print()
    console.print(
        f"{pad}[bold {PRIMARY}]{spec.name}[/bold {PRIMARY}]  [{DIM}]{spec.help_text}[/{DIM}]", highlight=False
    )
    console.print()

    if spec.aliases:
        aliases = ", ".join(spec.aliases)
        console.print(f"{pad}  [{DIM}]Aliases:[/{DIM}]  {aliases}", highlight=False, soft_wrap=True)

    if spec.subcommands:
        console.print(f"{pad}  [{DIM}]Subcommands:[/{DIM}]", highlight=False)
        for sub, desc in spec.subcommands.items():
            console.print(f"{pad}    [{PRIMARY}]{spec.name} {sub}[/{PRIMARY}]  [{DIM}]{desc}[/{DIM}]", highlight=False)

    console.print(f"{pad}  [{DIM}]Slash:[/{DIM}]  /{spec.name}", highlight=False)
    console.print()
    return True


def _help_main(pad: str, reg: CommandRegistry) -> None:
    """Full help for main screen."""
    console.print()

    # Quick start
    rows = [
        "Just type what you want — no slash needed.",
        f"[{DIM}]Open a project by name or number (1, 2, 3, ...).[/{DIM}]",
        f"[{DIM}]Tab autocompletes. Try: status, new, clone, help.[/{DIM}]",
    ]
    _box("Quick Start", rows, pad)
    console.print()

    # Commands by category
    w = _adaptive_width() - 4
    left_pad = _frame_left_pad() + 2
    cats = reg.categories()
    order = ["Projects", "Claude Code", "Git", "System", "Security", "Browser", "MCP", "Services", "Network", "Meta"]
    for cat in order:
        specs = cats.get(cat, [])
        if not specs:
            continue
        table = Table(show_header=False, box=None, padding=(0, 1), expand=True)
        table.add_column(style=f"bold {PRIMARY}", no_wrap=True, max_width=12)
        table.add_column(style="default", no_wrap=False)
        table.add_column(style=DIM, no_wrap=False)
        for spec in specs:
            alias = f"({spec.aliases[0]})" if spec.aliases else ""
            table.add_row(spec.name, spec.help_text, alias)
        p = Panel(
            table,
            title=f"[bold {PRIMARY}]{cat}[/bold {PRIMARY}]",
            title_align="left",
            border_style="dim",
            box=box.ROUNDED,
            padding=(0, 1),
            width=w,
        )
        console.print(Padding(p, (0, 0, 0, left_pad)), highlight=False)
        console.print()

    # Keyboard shortcuts
    shortcuts = [
        f"  [bold]1, 2...[/bold]  [{DIM}]Open project by number[/{DIM}]",
        f"  [bold]n[/bold]       [{DIM}]New project (/create)[/{DIM}]",
        f"  [bold]d[/bold]       [{DIM}]Delete project[/{DIM}]",
        f"  [bold]c[/bold]       [{DIM}]Claude Code (in project)[/{DIM}]",
        f"  [bold]g[/bold]       [{DIM}]lazygit (in project)[/{DIM}]",
        f"  [bold]b[/bold]       [{DIM}]Back to main screen[/{DIM}]",
        f"  [bold]Tab[/bold]     [{DIM}]Autocomplete[/{DIM}]",
    ]
    _box("Keyboard Shortcuts", shortcuts, pad)
    console.print()

    console.print(f"{pad}[{DIM}]Slash commands (/status, /help) also work.[/{DIM}]", highlight=False)
    console.print(f"{pad}[{DIM}]Try: help <command> for details.[/{DIM}]", highlight=False)
    console.print()


def _help_project(pad: str, reg: CommandRegistry) -> None:
    """Context-aware help when a project is open."""
    console.print()

    w = _adaptive_width() - 4
    left_pad = _frame_left_pad() + 2

    def _cmd_table(items: list[tuple[str, str]]) -> Table:
        table = Table(show_header=False, box=None, padding=(0, 1), expand=True)
        table.add_column(style=f"bold {PRIMARY}", no_wrap=True, max_width=12)
        table.add_column(style="default", no_wrap=False)
        for name, desc in items:
            table.add_row(name, desc)
        return table

    # Project actions
    items = [
        ("claude", "Start Claude Code here"),
        ("lazygit", "Visual git interface"),
        ("info", "Project details"),
        ("pull", "Pull latest changes"),
        ("push", "Push changes"),
        ("git log", "Recent commits"),
        ("delete", "Delete this project"),
        ("back", "Return to overview"),
    ]
    p = Panel(
        _cmd_table(items),
        title=f"[bold {PRIMARY}]In This Project[/bold {PRIMARY}]",
        title_align="left",
        border_style="dim",
        box=box.ROUNDED,
        padding=(0, 1),
        width=w,
    )
    console.print(Padding(p, (0, 0, 0, left_pad)), highlight=False)
    console.print()

    # Other commands
    items = [
        ("status", "System overview"),
        ("health", "Diagnostics"),
        ("docker", "Containers"),
        ("repos", "All projects"),
        ("n8n", "Workflow automation"),
        ("help", "Full help"),
    ]
    p = Panel(
        _cmd_table(items),
        title=f"[bold {PRIMARY}]Also Available[/bold {PRIMARY}]",
        title_align="left",
        border_style="dim",
        box=box.ROUNDED,
        padding=(0, 1),
        width=w,
    )
    console.print(Padding(p, (0, 0, 0, left_pad)), highlight=False)
    console.print()

    console.print(f"{pad}[{DIM}]Just type what you need.[/{DIM}]", highlight=False)
    console.print()


def cmd_help(state: TuiState, args: list[str]) -> CommandResult:
    pad = content_pad()
    reg: CommandRegistry = state.registry

    # help <command> — show single command detail
    if args:
        found = _cmd_detail(args[0], pad, reg)
        if not found:
            console.print(
                f"{pad}[{DIM}]Unknown command: {args[0]}. Try 'help' for all commands.[/{DIM}]", highlight=False
            )
        return CommandResult(ok=True, style="silent")

    # Context-aware help
    if state.screen == Screen.PROJECT or state.active_project:
        _help_project(pad, reg)
    else:
        _help_main(pad, reg)

    return CommandResult(ok=True, style="silent")


# ---------------------------------------------------------------------------
# /exit
# ---------------------------------------------------------------------------


def cmd_exit(_: TuiState, __: list[str]) -> CommandResult:
    pad = content_pad()
    console.print(f"{pad}[{DIM}]See you later. System standing by.[/{DIM}]", highlight=False)
    return CommandResult(ok=True, quit_app=True, style="silent")


# ---------------------------------------------------------------------------
# /welcome — re-trigger onboarding
# ---------------------------------------------------------------------------


def cmd_welcome(state: TuiState, _: list[str]) -> CommandResult:
    """Re-trigger the onboarding wizard."""
    from arasul_tui.core.onboarding import show_welcome

    return show_welcome()
