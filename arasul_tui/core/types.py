from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from arasul_tui.core.state import TuiState


PendingHandler = Callable[["TuiState", str], "CommandResult"]


@dataclass
class CommandResult:
    ok: bool
    lines: list[str] = field(default_factory=list)
    refresh: bool = False
    quit_app: bool = False
    launch_command: str | None = None
    launch_cwd: Path | None = None
    prompt: str | None = None
    pending_handler: PendingHandler | None = None
    style: str | None = None
    wizard_step: tuple[int, int, str] | None = None
