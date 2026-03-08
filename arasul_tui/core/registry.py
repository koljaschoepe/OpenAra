from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from arasul_tui.core.state import TuiState
from arasul_tui.core.types import CommandResult

Handler = Callable[[TuiState, list[str]], CommandResult]


@dataclass
class CommandSpec:
    name: str
    handler: Handler
    help_text: str
    category: str = ""
    subcommands: dict[str, str] | None = None
    aliases: list[str] = field(default_factory=list)


class CommandRegistry:
    def __init__(self) -> None:
        self._commands: dict[str, CommandSpec] = {}
        self._alias_map: dict[str, str] = {}  # alias -> command name

    def register(self, spec: CommandSpec) -> None:
        self._commands[spec.name] = spec
        for alias in spec.aliases:
            self._alias_map[alias.lower()] = spec.name

    def get(self, name: str) -> CommandSpec | None:
        return self._commands.get(name)

    def names(self) -> list[str]:
        return sorted(self._commands.keys())

    def specs(self) -> list[CommandSpec]:
        return [self._commands[n] for n in self.names()]

    def categories(self) -> dict[str, list[CommandSpec]]:
        """Return specs grouped by category, preserving order."""
        cats: dict[str, list[CommandSpec]] = {}
        for spec in self.specs():
            cat = spec.category or "Other"
            cats.setdefault(cat, []).append(spec)
        return cats

    def resolve(self, text: str) -> tuple[CommandSpec | None, list[str]]:
        """Resolve natural language or command input to a CommandSpec + args.

        Tries in order:
        1. Exact command name match
        2. Exact alias match (single or multi-word) — if alias is a subcommand, pass it as arg
        3. Unique prefix match on command names (unique only)
        4. Fuzzy substring match on names + aliases

        Returns (spec, remaining_args) or (None, []).
        """
        words = text.lower().split()
        if not words:
            return None, []

        # 1. Exact command name
        spec = self._commands.get(words[0])
        if spec:
            return spec, words[1:]

        # 2. Multi-word alias match (try longest first)
        for length in range(min(len(words), 4), 0, -1):
            phrase = " ".join(words[:length])
            cmd_name = self._alias_map.get(phrase)
            if cmd_name:
                spec = self._commands.get(cmd_name)
                if spec:
                    args = words[length:]
                    # If the alias word is a subcommand of the target, prepend it
                    if spec.subcommands and phrase in spec.subcommands:
                        args = [phrase] + args
                    return spec, args

        # 3. Unique prefix match on command names
        prefixes = [n for n in self._commands if n.startswith(words[0])]
        if len(prefixes) == 1:
            spec = self._commands[prefixes[0]]
            return spec, words[1:]

        # 4. Fuzzy: substring match (only for queries with 2+ chars to avoid false positives)
        if len(words[0]) >= 2:
            for word in words:
                if len(word) < 2:
                    continue
                for name, spec in self._commands.items():
                    if word in name or name in word:
                        remaining = [w for w in words if w != word]
                        return spec, remaining
                for alias, cmd_name in self._alias_map.items():
                    if word in alias.split():
                        spec = self._commands.get(cmd_name)
                        if spec:
                            remaining = [w for w in words if w != word]
                            # Subcommand forwarding for fuzzy matches too
                            if spec.subcommands and word in spec.subcommands:
                                remaining = [word] + remaining
                            return spec, remaining

        return None, []
