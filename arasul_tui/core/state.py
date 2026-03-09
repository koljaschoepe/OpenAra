from __future__ import annotations

import getpass
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


def _safe_username() -> str:
    try:
        return getpass.getuser()
    except (KeyError, ImportError):
        return os.environ.get("USER", "user")


def default_project_root() -> Path:
    from arasul_tui.core.platform import get_platform

    return get_platform().project_root


def _default_display_name() -> str:
    from arasul_tui.core.config import get_display_name

    return get_display_name()


class Screen(Enum):
    MAIN = "main"
    PROJECT = "project"


@dataclass
class TuiState:
    user: str = field(default_factory=_safe_username)
    display_name: str = field(default_factory=_default_display_name)
    active_project: Path | None = None
    project_root: Path = field(default_factory=default_project_root)
    first_run: bool = True
    screen: Screen = Screen.MAIN
    registry: Any = field(default=None, repr=False)

    # Generic wizard state dict (replaces individual _wizard_* fields)
    _wizard: dict[str, Any] = field(default_factory=dict, repr=False)

    # Legacy wizard state (backward compat — delegated to _wizard dict)
    @property
    def _wizard_token(self) -> str | None:
        return self._wizard.get("token")

    @_wizard_token.setter
    def _wizard_token(self, value: str | None) -> None:
        self._wizard["token"] = value

    @property
    def _wizard_uuid(self) -> str | None:
        return self._wizard.get("uuid")

    @_wizard_uuid.setter
    def _wizard_uuid(self, value: str | None) -> None:
        self._wizard["uuid"] = value

    @property
    def _delete_target(self) -> Any:
        return self._wizard.get("delete_target")

    @_delete_target.setter
    def _delete_target(self, value: Any) -> None:
        self._wizard["delete_target"] = value
