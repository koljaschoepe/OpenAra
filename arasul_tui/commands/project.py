from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from arasul_tui.core.projects import (
    register_project,
    unregister_project,
)
from arasul_tui.core.state import TuiState
from arasul_tui.core.templates import (
    create_conda_env,
    get_template,
    install_miniforge,
    is_miniforge_installed,
    list_available_templates,
    remove_conda_env,
    scaffold_project,
)
from arasul_tui.core.types import CommandResult
from arasul_tui.core.ui import (
    console,
    content_pad,
    content_width,
    print_error,
    print_info,
    print_styled_panel,
    print_success,
    print_warning,
    spinner_run,
    suggest_next,
    truncate,
)


def _task_summary(project: Path) -> str | None:
    """Count items per section in docs/tasks.md."""
    tasks_file = project / "docs" / "tasks.md"
    if not tasks_file.exists():
        return None
    try:
        text = tasks_file.read_text()
    except OSError:
        return None
    counts: dict[str, int] = {}
    current_section = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            current_section = stripped[3:].strip().lower()
        elif stripped.startswith("- ") and current_section:
            counts[current_section] = counts.get(current_section, 0) + 1
    if not counts:
        return None
    parts = []
    for key in ("in progress", "todo", "done"):
        if key in counts:
            parts.append(f"{counts[key]} {key}")
    return ", ".join(parts) if parts else None


def _count_doc_entries(filepath: Path) -> int:
    """Count non-comment list entries in a docs markdown file."""
    if not filepath.exists():
        return 0
    try:
        text = filepath.read_text()
    except OSError:
        return 0
    count = 0
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- ") and not stripped.startswith("<!-- "):
            count += 1
    return count


def _project_root(state: TuiState) -> Path | None:
    root = state.project_root
    try:
        root.mkdir(parents=True, exist_ok=True)
        return root
    except OSError:
        return None


def _project_dirs(root: Path) -> list[Path]:
    try:
        return sorted([p for p in root.iterdir() if p.is_dir()], key=lambda p: p.name.lower())
    except OSError:
        return []


def _is_safe_name(name: str) -> bool:
    """Reject names that could escape the project root."""
    return bool(name and "/" not in name and "\\" not in name and not name.startswith(".") and ".." not in name)


def _validate_project_path(target: Path, root: Path) -> str | None:
    """Return error message if path is invalid, else None."""
    if not target.resolve().is_relative_to(root.resolve()):
        return "Path outside project root is not allowed."
    return None


# ---------------------------------------------------------------------------
# /open
# ---------------------------------------------------------------------------


def cmd_open(state: TuiState, args: list[str]) -> CommandResult:
    root = state.project_root
    if not root.exists():
        print_error(f"Project root not found: {root}")
        return CommandResult(ok=False, style="silent")
    if not args:
        names = [p.name for p in _project_dirs(root)]
        if not names:
            print_warning("No projects found.")
            print_info("Type [bold]new[/bold] to create one, or [bold]clone[/bold] to grab a repo.")
            return CommandResult(ok=False, style="silent")
        print_info("Type a project name or number to open it.")
        return CommandResult(ok=False, style="silent")

    name = args[0]
    target = (root / name).resolve()
    path_err = _validate_project_path(target, root)
    if path_err:
        print_error(path_err)
        return CommandResult(ok=False, style="silent")
    if not target.exists() or not target.is_dir():
        print_error(f"Project not found: [bold]{name}[/bold]")
        return CommandResult(ok=False, style="silent")
    state.active_project = target
    return CommandResult(ok=True, style="silent", refresh=True)


# ---------------------------------------------------------------------------
# /create
# ---------------------------------------------------------------------------


def _create_finish(state: TuiState, user_input: str) -> CommandResult:
    name = user_input.strip().replace(" ", "-")
    if not _is_safe_name(name):
        print_error("Invalid project name.")
        print_info("Use letters, numbers, and hyphens (e.g., [bold]my-app[/bold])")
        return CommandResult(ok=False, style="silent")
    root = _project_root(state)
    if not root:
        print_error(f"Project root not writable: {state.project_root}")
        return CommandResult(ok=False, style="silent")
    target = (root / name).resolve()
    path_err = _validate_project_path(target, root)
    if path_err:
        print_error(path_err)
        return CommandResult(ok=False, style="silent")
    if target.exists():
        print_error(f"Project already exists: {target}")
        return CommandResult(ok=False, style="silent")
    target.mkdir(parents=True, exist_ok=False)
    register_project(name=name, path=target, provider_default="claude")

    # n8n project scaffolding
    from arasul_tui.core.n8n_project import is_n8n_project_name, scaffold_n8n_project

    if is_n8n_project_name(name):
        from arasul_tui.core.scaffold import scaffold_defaults

        scaffold_defaults(target, name, skip_claude_md=True)
        scaffold_n8n_project(target)
        print_success(f"n8n project created: [bold]{name}[/bold]")
        print_info("CLAUDE.md and guardrails configured.")
        print_info("Subdirs: [dim]workflows/[/dim], [dim]docs/[/dim]")
    else:
        from arasul_tui.core.scaffold import scaffold_defaults

        scaffold_defaults(target, name)
        print_success(f"Project created: [bold]{name}[/bold]")

    state.active_project = target
    print_info(f"Path: [dim]{target}[/dim]")
    return CommandResult(ok=True, style="silent", refresh=True)


def _create_template(state: TuiState, name: str, template_name: str) -> CommandResult:
    """Create a project with a template (conda env + starter files)."""
    template = get_template(template_name)
    available = list_available_templates()
    if not template or template not in available:
        valid = ", ".join(f"[bold]{t.name}[/bold]" for t in available)
        if template and template not in available:
            print_error(f"Template [bold]{template_name}[/bold] requires CUDA (not available on this device)")
        else:
            print_error(f"Unknown template: [bold]{template_name}[/bold]")
        print_info(f"Available: {valid}")
        return CommandResult(ok=False, style="silent")

    root = _project_root(state)
    if not root:
        print_error(f"Project root not writable: {state.project_root}")
        return CommandResult(ok=False, style="silent")
    target = (root / name).resolve()
    path_err = _validate_project_path(target, root)
    if path_err:
        print_error(path_err)
        return CommandResult(ok=False, style="silent")
    if target.exists():
        print_error(f"Project already exists: {target}")
        return CommandResult(ok=False, style="silent")

    # Step 1: Install Miniforge3 if needed
    if not is_miniforge_installed():
        print_info("Miniforge3 not found. Installing (one-time setup)...")
        ok, msg = spinner_run(
            "Installing Miniforge3...",
            lambda: install_miniforge(),
        )
        if not ok:
            print_error(f"Miniforge3 install failed: {msg}")
            return CommandResult(ok=False, style="silent")
        print_success("Miniforge3 installed")

    # Step 2: Create project directory
    target.mkdir(parents=True, exist_ok=False)

    # Step 3: Scaffold template files + .claude/ defaults
    print_info(f"Template: [bold]{template.label}[/bold]")
    ok, msg = scaffold_project(target, name, template)
    if not ok:
        print_error(f"Scaffold failed: {msg}")
        shutil.rmtree(target, ignore_errors=True)
        return CommandResult(ok=False, style="silent")

    from arasul_tui.core.scaffold import scaffold_defaults

    scaffold_defaults(target, name, skip_claude_md=True)

    # Step 4: Create conda environment
    def _do_env() -> tuple[bool, str]:
        return create_conda_env(name, template)

    try:
        ok, msg = spinner_run(
            f"Creating conda env [bold]{name}[/bold]...",
            _do_env,
        )
    except Exception as exc:
        print_error(f"Environment creation failed: {exc}")
        shutil.rmtree(target, ignore_errors=True)
        return CommandResult(ok=False, style="silent")

    if not ok:
        print_error(f"Environment creation failed: {msg}")
        print_warning("Project dir created but env is missing.")
        print_info("Try [bold]/delete[/bold] then [bold]/create[/bold] again, or fix the env manually.")
        # Still register — user might want to fix it
    else:
        print_success("conda environment ready")

    # Step 5: Register
    register_project(name=name, path=target, provider_default="claude")
    state.active_project = target

    console.print()
    print_success(f"Project [bold]{name}[/bold] created ({template.label})")
    print_info(f"Path: [dim]{target}[/dim]")
    from arasul_tui.core.platform import get_platform

    env_path = get_platform().storage.mount / "envs" / name
    print_info(f"Env: [dim]{env_path}[/dim]")
    print_info("Press [bold]c[/bold] to open in Claude Code")
    return CommandResult(ok=True, style="silent", refresh=True)


def cmd_create(state: TuiState, args: list[str]) -> CommandResult:
    # Parse --type flag
    template_name = None
    remaining_args = []
    i = 0
    while i < len(args):
        if args[i] == "--type" and i + 1 < len(args):
            template_name = args[i + 1]
            i += 2
        else:
            remaining_args.append(args[i])
            i += 1

    # Template creation: /create name --type template
    if template_name and remaining_args:
        name = remaining_args[0].strip().replace(" ", "-")
        if not _is_safe_name(name):
            print_error("Invalid project name.")
            print_info("Use letters, numbers, and hyphens (e.g., [bold]my-app[/bold])")
            return CommandResult(ok=False, style="silent")
        return _create_template(state, name, template_name)

    # Template but no name: ask for name, then create with template
    if template_name:
        state._wizard["template_name"] = template_name

        def _create_template_finish(state: TuiState, user_input: str) -> CommandResult:
            tpl = state._wizard.pop("template_name", None)
            if not tpl:
                print_error("Template selection lost. Try again.")
                return CommandResult(ok=False, style="silent")
            name = user_input.strip().replace(" ", "-")
            if not _is_safe_name(name):
                print_error("Invalid project name.")
                return CommandResult(ok=False, style="silent")
            return _create_template(state, name, tpl)

        print_info("What should the new project be called?")
        return CommandResult(
            ok=True,
            style="silent",
            prompt="Name",
            pending_handler=_create_template_finish,
            wizard_step=(1, 1, "Project"),
        )

    # Regular creation (unchanged)
    if remaining_args:
        return _create_finish(state, remaining_args[0])
    print_info("What should the new project be called?")
    return CommandResult(
        ok=True,
        style="silent",
        prompt="Name",
        pending_handler=_create_finish,
        wizard_step=(1, 1, "Project"),
    )


# ---------------------------------------------------------------------------
# /clone
# ---------------------------------------------------------------------------


def _clone_finish(state: TuiState, user_input: str) -> CommandResult:
    url = user_input.strip()
    if not url:
        print_error("URL must not be empty.")
        return CommandResult(ok=False, style="silent")

    _GIT_URL_RE = re.compile(
        r"^("
        r"https?://[\w.\-]+(:\d+)?/[\w.\-/]+"  # HTTPS with optional port
        r"|git@[\w.\-]+:[\w.\-/]+"  # SSH shorthand
        r"|ssh://[\w@.\-]+(:\d+)?/[\w.\-/]+"  # SSH with scheme
        r")$"
    )
    if not _GIT_URL_RE.match(url):
        print_error("Invalid URL. Expected: [dim]https://github.com/user/repo[/dim]")
        return CommandResult(ok=False, style="silent")

    repo_name = url.rstrip("/").split("/")[-1].removesuffix(".git")
    if not _is_safe_name(repo_name):
        print_error("Could not derive a safe repo name from URL.")
        return CommandResult(ok=False, style="silent")

    root = _project_root(state)
    if not root:
        print_error(f"Project root not writable: {state.project_root}")
        return CommandResult(ok=False, style="silent")

    target = (root / repo_name).resolve()
    path_err = _validate_project_path(target, root)
    if path_err:
        print_error(path_err)
        return CommandResult(ok=False, style="silent")
    if target.exists():
        print_error(f"Directory already exists: [bold]{repo_name}[/bold]")
        return CommandResult(ok=False, style="silent")

    def _do_clone() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "clone", url, str(target)],
            capture_output=True,
            text=True,
            timeout=120,
        )

    try:
        result = spinner_run(f"Cloning [bold]{repo_name}[/bold] ...", _do_clone)
    except (subprocess.TimeoutExpired, OSError) as exc:
        shutil.rmtree(target, ignore_errors=True)
        print_error(f"Clone failed: {exc}")
        return CommandResult(ok=False, style="silent")

    if result.returncode != 0:
        shutil.rmtree(target, ignore_errors=True)
        err = (result.stderr or result.stdout or "").strip()
        print_error(f"git clone failed: {err}")
        return CommandResult(ok=False, style="silent")

    register_project(name=repo_name, path=target, provider_default="claude")

    # Add missing .claude/ defaults (merge strategy: never overwrite existing files)
    from arasul_tui.core.scaffold import scaffold_clone_defaults

    scaffold_clone_defaults(target, repo_name)

    state.active_project = target
    print_success(f"Repo cloned: [bold]{repo_name}[/bold]")
    print_info(f"Path: [dim]{target}[/dim]")
    suggest_next(
        f"Open it: [bold]/open {repo_name}[/bold]",
        "Start coding: press [bold]c[/bold] to launch Claude Code",
    )
    return CommandResult(ok=True, style="silent", refresh=True)


def cmd_clone(state: TuiState, args: list[str]) -> CommandResult:
    if args:
        return _clone_finish(state, args[0])
    print_info("Enter GitHub URL (e.g. [dim]https://github.com/user/repo[/dim])")
    return CommandResult(
        ok=True,
        style="silent",
        prompt="URL",
        pending_handler=_clone_finish,
        wizard_step=(1, 1, "Clone"),
    )


# ---------------------------------------------------------------------------
# /delete
# ---------------------------------------------------------------------------


def _delete_confirm(state: TuiState, user_input: str) -> CommandResult:
    """Step 2: confirm deletion with y/n."""
    choice = user_input.strip().lower()
    target: Path | None = state._delete_target
    if target is None:
        print_error("Delete target lost. Please try again.")
        return CommandResult(ok=False, style="silent")

    if choice not in ("y", "yes", "j", "ja"):
        if choice in ("n", "no", "nein"):
            state._wizard.pop("delete_target", None)
            print_info("Cancelled.")
            return CommandResult(ok=True, style="silent")
        print_error("Please enter [bold]y[/bold] or [bold]n[/bold].")
        return CommandResult(
            ok=False,
            style="silent",
            prompt="Confirm",
            pending_handler=_delete_confirm,
            wizard_step=(2, 2, "Confirm"),
        )

    # Unregister first so the registry stays consistent even if
    # disk cleanup is interrupted (avoids ghost entries).
    unregister_project(target.name)

    if state.active_project and state.active_project.resolve() == target.resolve():
        state.active_project = None

    # Clean up wizard state
    state._wizard.pop("delete_target", None)

    try:
        shutil.rmtree(target)
    except OSError as exc:
        print_error(f"Directory removal failed: {exc}")
        print_warning("Project unregistered but files may remain on disk.")
        return CommandResult(ok=False, style="silent")

    # Clean up conda environment if it exists (only after successful rmtree)
    remove_conda_env(target.name)

    print_success(f"Project [bold]{target.name}[/bold] deleted.")
    suggest_next("View remaining: [bold]/repos[/bold]")
    return CommandResult(ok=True, style="silent", refresh=True)


def _delete_select(state: TuiState, user_input: str) -> CommandResult:
    """Step 1: select project by number."""
    num_str = user_input.strip()
    if not num_str.isdigit():
        print_error("Please enter a number.")
        return CommandResult(ok=False, style="silent")

    root = _project_root(state)
    if not root:
        print_error("Project root not available.")
        return CommandResult(ok=False, style="silent")

    projects = _project_dirs(root)
    num = int(num_str)
    if num < 1 or num > len(projects):
        print_error(f"Invalid number. Available: 1-{len(projects)}")
        return CommandResult(ok=False, style="silent")

    target = projects[num - 1]
    state._delete_target = target
    print_warning(f"Really delete [bold]{target.name}[/bold]? [dim](y/n)[/dim]")
    return CommandResult(
        ok=True,
        style="silent",
        prompt="Confirm",
        pending_handler=_delete_confirm,
        wizard_step=(2, 2, "Confirm"),
    )


def cmd_delete(state: TuiState, args: list[str]) -> CommandResult:
    root = _project_root(state)
    if not root:
        print_error(f"Project root not available: {state.project_root}")
        return CommandResult(ok=False, style="silent")

    projects = _project_dirs(root)
    if not projects:
        print_warning("No projects found.")
        return CommandResult(ok=False, style="silent")

    pad = content_pad()
    console.print()
    for i, p in enumerate(projects, 1):
        console.print(f"{pad}[cyan]{i}[/cyan]  {p.name}", highlight=False)
    console.print()
    print_info("Enter project number:")
    return CommandResult(
        ok=True,
        style="silent",
        prompt="Number",
        pending_handler=_delete_select,
        wizard_step=(1, 2, "Select"),
    )


# ---------------------------------------------------------------------------
# /info
# ---------------------------------------------------------------------------


def cmd_info(state: TuiState, args: list[str]) -> CommandResult:
    """Show detailed project info panel."""
    from arasul_tui.core.git_info import detect_language, get_disk_usage, get_git_info, get_readme_headline

    if args:
        root = state.project_root
        target = root / args[0]
        if not target.exists():
            print_error(f"Project not found: [bold]{args[0]}[/bold]")
            return CommandResult(ok=False, style="silent")
    elif state.active_project:
        target = state.active_project
    else:
        print_warning("No active project. Open one first, then try [bold]info[/bold].")
        return CommandResult(ok=False, style="silent")

    cw = content_width()
    git = get_git_info(target)
    rows: list[tuple[str, str]] = [("Name", target.name)]

    if git:
        branch_str = git.branch or "detached"
        if git.is_dirty:
            branch_str += " [yellow]*[/yellow]"
        rows.append(("Branch", branch_str))
        rows.append(("Status", "[yellow]modified[/yellow]" if git.is_dirty else "[green]clean[/green]"))
        if git.short_hash:
            msg = truncate(git.commit_message, cw - 10)
            rows.append(("Commit", f"{git.short_hash} {msg}"))
        if git.commit_time:
            rows.append(("Time", git.commit_time))
        if git.remote_url:
            rows.append(("Remote", truncate(git.remote_url, cw)))

    headline = get_readme_headline(target)
    if headline:
        rows.append(("About", truncate(headline, cw)))
    lang = detect_language(target)
    if lang:
        rows.append(("Lang", lang))
    disk = get_disk_usage(target)
    if disk:
        rows.append(("Disk", disk))
    rows.append(("Path", truncate(str(target), cw)))

    # Self-learning docs info
    task_summary = _task_summary(target)
    if task_summary:
        rows.append(("Tasks", task_summary))
    lessons_count = _count_doc_entries(target / "docs" / "lessons.md")
    if lessons_count:
        rows.append(("Lessons", f"{lessons_count} entries"))

    # n8n-specific info
    from arasul_tui.core.n8n_project import is_n8n_project_name

    if is_n8n_project_name(target.name):
        from arasul_tui.core.n8n_client import n8n_access_info, n8n_is_installed

        if n8n_is_installed():
            access = n8n_access_info()
            if access.is_running:
                rows.append(("n8n", "[green]running[/green]"))
            else:
                rows.append(("n8n", "[yellow]stopped[/yellow]"))
            if access.tailscale_url:
                rows.append(("Web UI", f"[cyan]{access.tailscale_url}[/cyan]"))
            else:
                rows.append(("Tunnel", f"[dim]{access.ssh_tunnel_cmd}[/dim]"))
                rows.append(("Web UI", f"[cyan]{access.local_url}[/cyan] (after tunnel)"))

    print_styled_panel(target.name, rows)
    return CommandResult(ok=True, style="silent")


# ---------------------------------------------------------------------------
# /repos
# ---------------------------------------------------------------------------


def cmd_repos(state: TuiState, _: list[str]) -> CommandResult:
    """Show all projects dashboard."""
    from arasul_tui.core.git_info import get_git_info

    root = state.project_root
    projects = _project_dirs(root)
    if not projects:
        print_warning("No projects found.")
        return CommandResult(ok=False, style="silent")

    rows: list[tuple[str, str]] = []
    for p in projects:
        git = get_git_info(p)
        if git:
            branch = truncate(git.branch or "?", 20)
            status = "[yellow]*[/yellow]" if git.is_dirty else "[green]✓[/green]"
            info = f"{branch} {status}  {git.commit_time}"
        else:
            info = "[dim]local[/dim]"
        active = " [cyan]←[/cyan]" if state.active_project and state.active_project.name == p.name else ""
        name = truncate(p.name, 28) + active
        rows.append((name, info))

    print_styled_panel("Projects", rows)
    return CommandResult(ok=True, style="silent")
