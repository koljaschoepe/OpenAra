"""Dashboard rendering: logo, system metrics, project list, headers."""

from __future__ import annotations

import shlex
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich.markup import escape as _escape_markup
from rich.text import Text

from arasul_tui.core.cache import cached_cmd, parallel_cmds
from arasul_tui.core.shell import run_cmd
from arasul_tui.core.theme import (
    DIM,
    LOGO_GRADIENT,
    PRIMARY,
    SUCCESS,
    WARNING,
)
from arasul_tui.core.ui.output import (
    _CHECK,
    _DEG,
    _DOT,
    MAX_WIDTH,
    TIER_FULL,
    TIER_MEDIUM,
    VERSION,
    _adaptive_width,
    _dim_hline,
    _frame_left_pad,
    _hline,
    console,
    content_pad,
)
from arasul_tui.core.ui.panels import _bar, _vis_len

if TYPE_CHECKING:
    from arasul_tui.core.state import TuiState


# ---------------------------------------------------------------------------
# Logo
# ---------------------------------------------------------------------------

LOGO = [
    "  \u2584\u2580\u2588 \u2588\u2580\u2588 \u2584\u2580\u2588 \u2588\u2580\u2580 \u2588 \u2588 \u2588  ",
    "  \u2588\u2580\u2588 \u2588\u2580\u2584 \u2588\u2580\u2588 \u2584\u2588 \u2588\u2584\u2588 \u2588\u2584\u2584",
]


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------


def _greeting(user: str) -> str:
    """Time-aware greeting for the user."""
    import datetime

    hour = datetime.datetime.now().hour
    name = user.capitalize()
    if hour < 6:
        return f"Still up, {name}?"
    if hour < 12:
        return f"Good morning, {name}."
    if hour < 17:
        return f"Good afternoon, {name}."
    if hour < 22:
        return f"Good evening, {name}."
    return f"Late session, {name}."


def _github_status() -> str:
    auth = cached_cmd("gh auth status 2>&1", timeout=4, ttl=120)
    if "Logged in" not in auth:
        return "[dim]not connected[/dim]"
    from arasul_tui.core.git_info import parse_gh_account

    account = parse_gh_account(auth)
    return f"[cyan]{_CHECK}[/cyan] {account}" if account else f"[cyan]{_CHECK}[/cyan]"


def get_default_interface() -> str:
    """Detect primary network interface dynamically."""
    iface = cached_cmd("ip route show default 2>/dev/null | awk '/default/{print $5}'")
    return iface or "eth0"


def _system_info() -> dict[str, Any]:
    """Gather system info in parallel. Returns dict of named values."""
    from arasul_tui.core.platform import get_platform

    platform = get_platform()

    try:
        import psutil

        vm = psutil.virtual_memory()
        ram = f"{vm.used // (1024 * 1024)}M / {vm.total // (1024 * 1024)}M"
        ram_pct = vm.percent
    except Exception:
        ram = cached_cmd("free -m | awk '/^Mem:/{printf \"%dM / %dM\", $3, $2}'") or "n/a"
        ram_pct = 0

    storage_path = shlex.quote(str(platform.storage.mount))
    cmds = {
        "disk": (f"df -h {storage_path} 2>/dev/null | awk 'NR==2{{print $3\"/\"$2}}'", 4),
        "disk_pct": (f"df {storage_path} 2>/dev/null | awk 'NR==2{{print $5}}' | tr -d '%'", 4),
        "temp": (
            "cat /sys/devices/virtual/thermal/thermal_zone0/temp 2>/dev/null | awk '{printf \"%.0f\", $1/1000}'",
            4,
        ),
        "ip": ("hostname -I 2>/dev/null | awk '{print $1}'", 4),
        "docker": ("docker ps -q 2>/dev/null | wc -l | tr -d ' '", 5),
    }

    # Platform-specific commands
    if platform.is_jetson:
        cmds["power"] = ("nvpmodel -q 2>/dev/null | head -1 | sed 's/NV Power Mode: //'", 4)
        cmds["gpu"] = ("cat /sys/devices/gpu.0/load 2>/dev/null", 4)
    elif platform.is_raspberry_pi:
        cmds["temp"] = ("vcgencmd measure_temp 2>/dev/null | awk -F'[=.]' '{print $2}'", 4)
        cmds["freq"] = (
            "vcgencmd measure_clock arm 2>/dev/null | awk -F= '{printf \"%.0f\", $2/1000000}'",
            4,
        )
        cmds["throttle"] = ("vcgencmd get_throttled 2>/dev/null | awk -F= '{print $2}'", 4)

    r = parallel_cmds(cmds)

    disk = r.get("disk", "")
    if not disk or disk.startswith("Error"):
        disk = cached_cmd("df -h / | awk 'NR==2{print $3\"/\"$2}'") or "n/a"

    disk_pct_str = r.get("disk_pct", "0")
    disk_pct = int(disk_pct_str) if disk_pct_str.isdigit() else 0

    temp = r.get("temp", "")
    temp_val = int(temp) if temp and temp.isdigit() else 0

    gpu = r.get("gpu", "")
    gpu_pct = int(gpu) // 10 if gpu and gpu.isdigit() else 0

    freq = r.get("freq", "")
    freq_mhz = int(freq) if freq and freq.isdigit() else 0

    throttle = r.get("throttle", "")
    throttled = bool(throttle and throttle != "0x0")

    return {
        "platform": platform.name,
        "ram": ram,
        "ram_pct": ram_pct,
        "disk": disk,
        "disk_pct": disk_pct,
        "temp": temp_val,
        "gpu_pct": gpu_pct,
        "power": r.get("power", ""),
        "ip": r.get("ip", "n/a"),
        "docker": r.get("docker", "0"),
        "freq_mhz": freq_mhz,
        "throttled": throttled,
    }


def project_list() -> list[str]:
    from arasul_tui.core.state import default_project_root

    try:
        return sorted([p.name for p in default_project_root().iterdir() if p.is_dir()], key=str.lower)
    except OSError:
        return []


def _project_detail(name: str) -> tuple[str, str, bool]:
    """Return (branch, commit_time, is_dirty) for a project."""
    from arasul_tui.core.state import default_project_root

    project = default_project_root() / name
    if not (project / ".git").exists():
        return ("", "", False)
    quoted = shlex.quote(str(project))

    r = parallel_cmds(
        {
            "branch": (f"git -C {quoted} symbolic-ref --short HEAD 2>/dev/null", 4),
            "dirty": (f"git -C {quoted} status --porcelain 2>/dev/null", 4),
            "time": (f"git -C {quoted} log -1 --format=%cr 2>/dev/null", 4),
        }
    )

    branch = r.get("branch", "")
    dirty_out = r.get("dirty", "")
    is_dirty = bool(dirty_out and not dirty_out.startswith("Error"))
    commit_time = r.get("time", "")

    return (branch, commit_time, is_dirty)


def _git_info_short(project: Path | None) -> str:
    if not project or not (project / ".git").exists():
        return ""
    quoted = shlex.quote(str(project))
    url = run_cmd(f"git -C {quoted} remote get-url origin 2>/dev/null")
    if not url:
        return "[dim]local[/dim]"
    host = "github" if "github" in url else "git"
    branch = run_cmd(f"git -C {quoted} symbolic-ref --short HEAD 2>/dev/null")
    if branch:
        return f"[dim]{host} {_DOT} {branch}[/dim]"
    return f"[dim]{host}[/dim]"


# ---------------------------------------------------------------------------
# Dashboard builder
# ---------------------------------------------------------------------------


def _build_full_dashboard(state: TuiState, content_w: int) -> list[str]:
    """Build the complete dashboard: greeting, system box, projects."""
    info = _system_info()
    lines: list[str] = []
    dot_sep = f" {_DOT} "
    plat = info.get("platform", "generic")

    # --- Greeting ---
    lines.append("")
    lines.append(f"  {_greeting(state.display_name or state.user)}")

    # --- Status subtitle ---
    status_parts: list[str] = [VERSION]
    power = info.get("power", "")
    if power:
        status_parts.append(power)
    elif plat == "raspberry_pi":
        from arasul_tui.core.platform import get_platform

        status_parts.append(get_platform().display_name)
    ip = info.get("ip", "")
    if ip and ip != "n/a":
        status_parts.append(ip)
    joined = dot_sep.join(status_parts)
    lines.append(f"  [{DIM}]{joined}[/{DIM}]")
    lines.append("")

    # --- System box ---
    box_w = min(content_w - 2, 46)
    bar_w = max(8, min(10, box_w // 5))
    _corner_tl = "\u256d"  # ╭
    _corner_tr = "\u256e"  # ╮
    _corner_bl = "\u2570"  # ╰
    _corner_br = "\u256f"  # ╯
    _vline = "\u2502"  # │

    box_top = f"  [{DIM}]{_corner_tl}{_hline(box_w)}{_corner_tr}[/{DIM}]"
    box_bot = f"  [{DIM}]{_corner_bl}{_hline(box_w)}{_corner_br}[/{DIM}]"
    lines.append(box_top)

    def _box_row_closed(content: str) -> str:
        vis = _vis_len(content)
        if vis > box_w:
            # Truncate to fit — use plain text to avoid broken markup after truncation
            try:
                t = Text.from_markup(content)
                t.truncate(box_w - 1)
                # Use plain text + ellipsis to prevent invalid markup from t.markup
                content = f"[{DIM}]{_escape_markup(t.plain)}\u2026[/{DIM}]"
            except Exception:
                content = content[: box_w - 1] + "\u2026"
            vis = _vis_len(content)
        pad_n = max(0, box_w - vis)
        return f"  [{DIM}]{_vline}[/{DIM}]{content}{' ' * pad_n}[{DIM}]{_vline}[/{DIM}]"

    def _metric_row(label: str, bar: str, detail: str) -> str:
        # Calculate available space for detail after label + bar + spacing
        bar_vis = _vis_len(bar)
        used = 2 + 5 + bar_vis + 2  # "  " + label(5) + bar + "  "
        avail = box_w - used
        detail_vis = _vis_len(detail)
        if detail_vis > avail and avail > 1:
            t = Text.from_markup(detail)
            t.truncate(max(1, avail - 1))
            detail = t.plain + "\u2026"
        return _box_row_closed(f"  {label:<5}{bar}  [{DIM}]{detail}[/{DIM}]")

    def _empty_row() -> str:
        return _box_row_closed("")

    ram_raw = info.get("ram_pct", 0)
    ram_pct = float(ram_raw) if isinstance(ram_raw, (int, float)) else 0.0
    lines.append(_metric_row("RAM", _bar(ram_pct, bar_w), info["ram"]))

    disk_raw = info.get("disk_pct", 0)
    disk_pct = float(disk_raw) if isinstance(disk_raw, (int, float)) else 0.0
    lines.append(_metric_row("Disk", _bar(disk_pct, bar_w), info["disk"]))

    temp = info.get("temp", 0)
    temp_pct = min(100, max(0, (temp - 20) * 100 // 80)) if temp else 0
    if temp:
        lines.append(_metric_row("Temp", _bar(temp_pct, bar_w), f"{temp}{_DEG}C"))

    if plat == "jetson":
        gpu_pct_val = info.get("gpu_pct", 0)
        if gpu_pct_val:
            lines.append(_metric_row("GPU", _bar(float(gpu_pct_val), bar_w), f"{gpu_pct_val}%"))
    elif plat == "raspberry_pi":
        freq = info.get("freq_mhz", 0)
        if freq:
            freq_pct = min(100, freq * 100 // 2500)
            lines.append(_metric_row("Freq", _bar(float(freq_pct), bar_w), f"{freq} MHz"))
        if info.get("throttled"):
            lines.append(_box_row_closed(f"  [{WARNING}]Throttled[/{WARNING}]"))

    lines.append(_empty_row())

    svc_parts: list[str] = []
    gh = _github_status()
    svc_parts.append(f"GitHub: {gh}")
    docker = info.get("docker", "0")
    if docker and docker != "0":
        svc_parts.append(f"Docker: {docker}")
    svc_line = dot_sep.join(svc_parts)
    # _box_row_closed handles truncation if too wide
    lines.append(_box_row_closed(f"  [{DIM}]{svc_line}[/{DIM}]"))

    lines.append(box_bot)

    # --- Projects ---
    lines.append("")
    lines.append("  [bold]Projects[/bold]")
    lines.append("")

    projects = project_list()
    for i, name in enumerate(projects, 1):
        branch, commit_time, is_dirty = _project_detail(name)
        # Escape user-controlled strings to prevent Rich markup injection
        safe_name = _escape_markup(name)
        disp_name = safe_name if len(safe_name) <= 28 else safe_name[:27] + "\u2026"
        parts: list[str] = []
        if branch:
            safe_branch = _escape_markup(branch)
            disp_branch = safe_branch if len(safe_branch) <= 20 else safe_branch[:19] + "\u2026"
            branch_str = f"[{DIM}]{disp_branch}[/{DIM}]"
            if is_dirty:
                parts.append(f"{branch_str} [{WARNING}]*[/{WARNING}]")
            else:
                parts.append(f"{branch_str} [{SUCCESS}]{_CHECK}[/{SUCCESS}]")
        if commit_time:
            safe_time = _escape_markup(commit_time)
            parts.append(f"[{DIM}]{safe_time}[/{DIM}]")
        detail = "  ".join(parts) if parts else f"[{DIM}]local[/{DIM}]"
        lines.append(f"  [{PRIMARY}]{i}[/{PRIMARY}]  {disp_name}  {detail}")

    if not projects:
        lines.append(f"  [{DIM}]No projects yet.[/{DIM}]")
        lines.append(f"  [{DIM}]Type 'new' to create one, or 'clone' to grab a repo.[/{DIM}]")

    # --- Contextual hints ---
    lines.append("")
    hints = _build_hints(projects)
    for hint in hints:
        lines.append(f"  [{DIM}]{hint}[/{DIM}]")

    return lines


def _build_hints(projects: list[str]) -> list[str]:
    """Build 2-3 contextual hint lines based on current state."""
    hints: list[str] = []

    if not projects:
        hints.append("Type 'new' to create a project, or 'clone' to grab a repo.")
    else:
        hints.append("Open a project by name or number.")

    # Check Claude auth
    from arasul_tui.core.auth import is_claude_configured

    if not is_claude_configured():
        hints.append("Run 'auth' to set up Claude Code.")
    elif not projects:
        pass  # already have a hint
    else:
        hints.append("Try 'status', 'new', or 'help'.")

    return hints


# ---------------------------------------------------------------------------
# Header variants
# ---------------------------------------------------------------------------


def _print_header_full(state: TuiState) -> None:
    """Full dashboard: frameless layout with gradient logo and boot animation."""
    w = _adaptive_width()
    content_w = w - 6
    pad = content_pad()

    console.print()

    animate = state.first_run
    for i, line in enumerate(LOGO):
        color = LOGO_GRADIENT[i % len(LOGO_GRADIENT)]
        console.print(f"{pad}{line}", style=f"bold {color}", highlight=False)
        if animate:
            time.sleep(0.06)

    dashboard = _build_full_dashboard(state, content_w)
    for line in dashboard:
        console.print(f"{pad}{line}", highlight=False)
    console.print()


def _print_header_medium(state: TuiState) -> None:
    """Medium header: compact logo + full dashboard."""
    content_w = min(console.width - 6, MAX_WIDTH - 6)
    pad = content_pad()

    console.print()
    for i, line in enumerate(LOGO):
        color = LOGO_GRADIENT[i % len(LOGO_GRADIENT)]
        console.print(f"{pad}{line}", style=f"bold {color}", highlight=False)
    dashboard = _build_full_dashboard(state, content_w)
    for line in dashboard:
        console.print(f"{pad}{line}", highlight=False)
    console.print()


def _print_header_compact(state: TuiState) -> None:
    """Compact header: text-only with mini bars."""
    pad = " " * _frame_left_pad()
    console.print()
    console.print(f"{pad}[bold {PRIMARY}]ARASUL[/bold {PRIMARY}] [{DIM}]{VERSION}[/{DIM}]", highlight=False)
    info = _system_info()
    ram_pct = float(info.get("ram_pct", 0))
    disk_pct = float(info.get("disk_pct", 0))
    console.print(f"{pad}RAM {_bar(ram_pct, 6)} [{DIM}]{info['ram']}[/{DIM}]", highlight=False)
    console.print(f"{pad}Disk {_bar(disk_pct, 6)} [{DIM}]{info['disk']}[/{DIM}]", highlight=False)
    projects = project_list()
    if projects:
        console.print(f"{pad}Projects: {len(projects)}", highlight=False)
    console.print()


def _print_project_screen(state: TuiState) -> None:
    """Dedicated project mini-dashboard when a project is open."""
    project = state.active_project
    if not project:
        return

    pad = content_pad()
    name = _escape_markup(project.name)

    console.print()
    console.print(f"{pad}[bold {PRIMARY}]{name}[/bold {PRIMARY}]", highlight=False)

    from arasul_tui.core.git_info import detect_language, get_disk_usage, get_git_info

    gi = get_git_info(project)
    lang = detect_language(project)
    disk = get_disk_usage(project)

    if gi:
        branch_color = WARNING if gi.is_dirty else SUCCESS
        dirty_mark = f" [{WARNING}]*[/{WARNING}]" if gi.is_dirty else ""
        safe_branch = _escape_markup(gi.branch)
        safe_hash = _escape_markup(gi.short_hash)
        console.print(
            f"{pad}  [{branch_color}]{safe_branch}[/{branch_color}]{dirty_mark}  [{DIM}]{safe_hash}[/{DIM}]",
            highlight=False,
        )
        if gi.commit_message:
            safe_msg = _escape_markup(gi.commit_message)
            safe_time = _escape_markup(gi.commit_time)
            console.print(
                f"{pad}  [{DIM}]{safe_msg}  {_DOT}  {safe_time}[/{DIM}]",
                highlight=False,
            )
    else:
        console.print(f"{pad}  [{DIM}]no git[/{DIM}]", highlight=False)

    detail_parts: list[str] = []
    if lang:
        detail_parts.append(lang)
    if disk:
        detail_parts.append(disk)
    if detail_parts:
        detail_line = f"  {_DOT}  ".join(detail_parts)
        console.print(f"{pad}  [{DIM}]{detail_line}[/{DIM}]", highlight=False)

    # n8n project: show status + access info
    from arasul_tui.core.n8n_project import is_n8n_project_name

    n8n_active = False
    access = None
    if is_n8n_project_name(name):
        from arasul_tui.core.n8n_client import n8n_access_info, n8n_is_installed

        if n8n_is_installed():
            n8n_active = True
            access = n8n_access_info()
            console.print()
            if access.is_running:
                status = f"[{SUCCESS}]n8n running[/{SUCCESS}]"
            else:
                status = f"[{WARNING}]n8n stopped[/{WARNING}]  [{DIM}]type [{PRIMARY}]n8n[/{PRIMARY}] to start[/{DIM}]"
            console.print(f"{pad}  {status}", highlight=False)

            if access.tailscale_url:
                console.print(
                    f"{pad}  [{DIM}]Open:[/{DIM}]  [{PRIMARY}]{access.tailscale_url}[/{PRIMARY}]",
                    highlight=False,
                )
            else:
                console.print(
                    f"{pad}  [{DIM}]From Mac:[/{DIM}]  [bold]{access.ssh_tunnel_cmd}[/bold]",
                    highlight=False,
                )
                console.print(
                    f"{pad}  [{DIM}]Then:[/{DIM}]    [{PRIMARY}]{access.local_url}[/{PRIMARY}]",
                    highlight=False,
                )

    hints: list[str] = []
    if n8n_active and access:
        if access.is_running:
            hints.append(f"[{PRIMARY}]n8n[/{PRIMARY}] for full status")
        else:
            hints.append(f"[{PRIMARY}]n8n[/{PRIMARY}] to start n8n")
    else:
        hints.append(f"[{PRIMARY}]claude[/{PRIMARY}] to start coding")
    if gi and gi.is_dirty:
        hints.append(f"[{PRIMARY}]push[/{PRIMARY}] to save changes")
    elif gi:
        hints.append(f"[{PRIMARY}]pull[/{PRIMARY}] to sync")
    else:
        hints.append(f"[{PRIMARY}]git[/{PRIMARY}] to set up version control")
    hints.append(f"[{PRIMARY}]back[/{PRIMARY}] to return")
    console.print()
    for hint in hints:
        console.print(f"{pad}  [{DIM}]{hint}[/{DIM}]", highlight=False)
    console.print()


# ---------------------------------------------------------------------------
# Public header and prompt
# ---------------------------------------------------------------------------


def print_header(state: TuiState, full: bool = True) -> None:
    """Print header. full=True for startup dashboard, full=False for inline context."""
    if not full:
        pad = content_pad()
        w = _adaptive_width() - 6
        parts: list[str] = []
        if state.active_project:
            name = _escape_markup(state.active_project.name)
            parts.append(f"[bold]{name}[/bold]")
            gi = _git_info_short(state.active_project)
            if gi:
                parts.append(gi)
        else:
            parts.append(f"[{DIM}]main[/{DIM}]")
        dot_sep = f" [{DIM}]{_DOT}[/{DIM}] "
        title_len = _vis_len(dot_sep.join(parts)) + 2
        side = max(1, (w - title_len) // 2)
        right_side = max(1, w - title_len - side)
        left = _dim_hline(side)
        right = _dim_hline(right_side)
        joined = dot_sep.join(parts)
        console.print(
            f"{pad}{left} {joined} {right}",
            highlight=False,
        )
        return

    if state.active_project:
        _print_project_screen(state)
        return

    if console.width >= TIER_FULL:
        _print_header_full(state)
    elif console.width >= TIER_MEDIUM:
        _print_header_medium(state)
    else:
        _print_header_compact(state)


def build_prompt(state: TuiState, wizard_step: tuple[int, int, str] | None = None) -> str:
    """Returns prompt_toolkit HTML markup (not Rich markup)."""
    pad = " " * (_frame_left_pad() + 2)

    if wizard_step:
        cur, total, label = wizard_step
        return f"{pad}<style fg='yellow'>[{cur}/{total}]</style> {label} &gt; "

    if state.active_project:
        import html

        name = html.escape(state.active_project.name)
        return f"{pad}<b><style fg='ansicyan'>{name}</style></b> &gt; "

    return f"{pad}<b>&gt;</b> "
