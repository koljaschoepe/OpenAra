"""UI package — re-exports all public symbols for backward compatibility.

Modules:
    output    — Console instance, print helpers, spinner
    panels    — Styled panels, checklists, progress, KV tables
    dashboard — Logo, system metrics, project list, headers, prompt
"""

from __future__ import annotations

# dashboard.py — dashboard, headers, prompt
from arasul_tui.core.ui.dashboard import (
    LOGO,
    build_prompt,
    get_default_interface,
    print_header,
    project_list,
)

# output.py — core console & print functions
from arasul_tui.core.ui.output import (
    VERSION,
    _adaptive_width,
    _frame_left_pad,
    console,
    content_pad,
    content_width,
    print_error,
    print_info,
    print_result,
    print_separator,
    print_success,
    print_warning,
    spinner_run,
    suggest_next,
    truncate,
)

# panels.py — styled display components
from arasul_tui.core.ui.panels import (
    print_checklist,
    print_kv,
    print_progress,
    print_step,
    print_styled_panel,
)

__all__ = [
    # output
    "VERSION",
    "_adaptive_width",
    "_frame_left_pad",
    "console",
    "content_pad",
    "content_width",
    "print_error",
    "print_info",
    "print_result",
    "print_separator",
    "print_success",
    "print_warning",
    "suggest_next",
    "spinner_run",
    "truncate",
    # panels
    "print_checklist",
    "print_kv",
    "print_progress",
    "print_step",
    "print_styled_panel",
    # dashboard
    "LOGO",
    "build_prompt",
    "get_default_interface",
    "print_header",
    "project_list",
]
