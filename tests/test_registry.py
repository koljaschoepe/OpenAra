from __future__ import annotations

from arasul_tui.core.registry import CommandRegistry, CommandSpec
from arasul_tui.core.state import TuiState
from arasul_tui.core.types import CommandResult


def _noop_handler(state: TuiState, args: list[str]) -> CommandResult:
    return CommandResult(ok=True)


def test_register_and_get():
    reg = CommandRegistry()
    spec = CommandSpec("test", _noop_handler, "A test command")
    reg.register(spec)
    assert reg.get("test") is spec
    assert reg.get("nonexistent") is None


def test_names_sorted():
    reg = CommandRegistry()
    reg.register(CommandSpec("zebra", _noop_handler, "Z"))
    reg.register(CommandSpec("alpha", _noop_handler, "A"))
    reg.register(CommandSpec("middle", _noop_handler, "M"))
    assert reg.names() == ["alpha", "middle", "zebra"]


def test_specs_order():
    reg = CommandRegistry()
    reg.register(CommandSpec("beta", _noop_handler, "B"))
    reg.register(CommandSpec("alpha", _noop_handler, "A"))
    specs = reg.specs()
    assert [s.name for s in specs] == ["alpha", "beta"]


def test_categories():
    reg = CommandRegistry()
    reg.register(CommandSpec("help", _noop_handler, "Help", category="Meta"))
    reg.register(CommandSpec("status", _noop_handler, "Status", category="System"))
    reg.register(CommandSpec("health", _noop_handler, "Health", category="System"))

    cats = reg.categories()
    assert "Meta" in cats
    assert "System" in cats
    assert len(cats["System"]) == 2


def test_category_field():
    spec = CommandSpec("test", _noop_handler, "Test", category="Custom")
    assert spec.category == "Custom"


def test_subcommands_field():
    spec = CommandSpec("git", _noop_handler, "Git", subcommands={"pull": "Pull", "push": "Push"})
    assert spec.subcommands == {"pull": "Pull", "push": "Push"}


def test_resolve_exact_name():
    reg = CommandRegistry()
    reg.register(CommandSpec("status", _noop_handler, "Status"))
    spec, args = reg.resolve("status")
    assert spec is not None
    assert spec.name == "status"
    assert args == []


def test_resolve_with_args():
    reg = CommandRegistry()
    reg.register(CommandSpec("open", _noop_handler, "Open"))
    spec, args = reg.resolve("open myproject")
    assert spec is not None
    assert spec.name == "open"
    assert args == ["myproject"]


def test_resolve_alias():
    reg = CommandRegistry()
    reg.register(CommandSpec("create", _noop_handler, "Create", aliases=["new", "new project"]))
    spec, args = reg.resolve("new")
    assert spec is not None
    assert spec.name == "create"

    spec2, args2 = reg.resolve("new project")
    assert spec2 is not None
    assert spec2.name == "create"
    assert args2 == []


def test_resolve_subcommand_alias():
    reg = CommandRegistry()
    reg.register(
        CommandSpec(
            "git",
            _noop_handler,
            "Git",
            aliases=["pull", "push"],
            subcommands={"pull": "Pull", "push": "Push"},
        )
    )
    spec, args = reg.resolve("pull")
    assert spec is not None
    assert spec.name == "git"
    assert args == ["pull"]


def test_resolve_prefix():
    reg = CommandRegistry()
    reg.register(CommandSpec("status", _noop_handler, "Status"))
    reg.register(CommandSpec("setup", _noop_handler, "Setup"))

    # "stat" is unique prefix
    spec, _ = reg.resolve("stat")
    assert spec is not None
    assert spec.name == "status"

    # "setu" is unique prefix
    spec2, _ = reg.resolve("setu")
    assert spec2 is not None
    assert spec2.name == "setup"


def test_resolve_no_match():
    reg = CommandRegistry()
    reg.register(CommandSpec("status", _noop_handler, "Status"))
    spec, _ = reg.resolve("nonsense")
    assert spec is None


def test_resolve_single_char_no_fuzzy():
    """Single characters should not fuzzy-match to avoid false positives."""
    reg = CommandRegistry()
    reg.register(CommandSpec("open", _noop_handler, "Open"))
    spec, _ = reg.resolve("n")
    assert spec is None
