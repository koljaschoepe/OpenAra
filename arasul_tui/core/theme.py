"""Arasul TUI color theme — consistent sci-fi aesthetic."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Semantic color tokens (Rich markup names)
# Use these throughout the codebase instead of hardcoded color strings.
# They map to Rich style names that work across terminal themes.
# ---------------------------------------------------------------------------

PRIMARY = "cyan"  # Main accent — logo, prompts, active items
SUCCESS = "green"  # Checkmarks, clean status, success messages
WARNING = "yellow"  # Warnings, dirty status, caution
ERROR = "red"  # Errors, failures, critical
DIM = "dim"  # Muted text, timestamps, paths

# Bar characters (modern block style)
BAR_FILLED = "\u25b0"  # ▰
BAR_EMPTY = "\u25b1"  # ▱

# Status indicators
ICON_OK = f"[{SUCCESS}]\u2713[/{SUCCESS}]"  # ✓
ICON_WARN = f"[{WARNING}]~[/{WARNING}]"  # ~
ICON_FAIL = f"[{ERROR}]\u2717[/{ERROR}]"  # ✗
ICON_ARROW = f"[{PRIMARY}]\u2192[/{PRIMARY}]"  # →
ICON_DOT_ON = f"[{SUCCESS}]\u25cf[/{SUCCESS}]"  # ●
ICON_DOT_OFF = f"[{DIM}]\u25cb[/{DIM}]"  # ○

# Logo gradient — top to bottom (7 lines)
LOGO_GRADIENT = [
    "#00d4ff",
    "#10c0ff",
    "#20acff",
    "#3098ff",
    "#4088ff",
    "#4c7cff",
    "#5870ff",
]
