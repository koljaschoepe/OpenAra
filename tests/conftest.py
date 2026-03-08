from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from arasul_tui.core.router import REGISTRY
from arasul_tui.core.state import TuiState


@pytest.fixture(autouse=True)
def _mock_console_width():
    """Ensure console.width returns a real int in tests (no terminal)."""
    with patch("arasul_tui.core.ui.output.console") as mock_console:
        mock_console.width = 100
        mock_console.print = lambda *a, **kw: None
        yield mock_console


@pytest.fixture
def tmp_project_root(tmp_path: Path) -> Path:
    """Provide a temporary project root directory."""
    root = tmp_path / "projects"
    root.mkdir()
    return root


@pytest.fixture
def state(tmp_project_root: Path) -> TuiState:
    """Provide a TuiState with a temporary project root and registry."""
    s = TuiState(registry=REGISTRY)
    s.project_root = tmp_project_root
    return s


@pytest.fixture
def state_with_projects(state: TuiState) -> TuiState:
    """Provide a TuiState with some test projects created."""
    for name in ["alpha", "beta", "gamma"]:
        (state.project_root / name).mkdir()
    return state
