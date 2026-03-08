from __future__ import annotations

import shlex
import socket
import subprocess
from pathlib import Path

from arasul_tui.core.git_info import parse_gh_account
from arasul_tui.core.shell import run_cmd
from arasul_tui.core.state import TuiState
from arasul_tui.core.types import CommandResult
from arasul_tui.core.ui import (
    console,
    content_pad,
    content_width,
    print_error,
    print_info,
    print_kv,
    print_step,
    print_styled_panel,
    print_success,
    print_warning,
    spinner_run,
    truncate,
)

# ---------------------------------------------------------------------------
# Git status helpers (from original commands.py)
# ---------------------------------------------------------------------------


def _git_status_lines() -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []

    gh = run_cmd("command -v gh && gh --version | head -1", timeout=3)
    if "gh version" in gh:
        ver = gh.splitlines()[-1].strip()
        rows.append(("gh CLI", f"[green]✓[/green] {ver}"))
    else:
        rows.append(("gh CLI", "[red]✗[/red] not installed"))

    auth = run_cmd("gh auth status 2>&1", timeout=5)
    if "Logged in" in auth:
        account = parse_gh_account(auth)
        rows.append(("Auth", f"[green]✓[/green] {account}" if account else "[green]✓[/green] logged in"))
    else:
        rows.append(("Auth", "[red]✗[/red] not logged in"))

    name = run_cmd("git config --global user.name")
    email = run_cmd("git config --global user.email")
    rows.append(("Git Name", name or "[dim]not set[/dim]"))
    rows.append(("Git Email", email or "[dim]not set[/dim]"))

    ssh_key = Path.home() / ".ssh" / "id_ed25519.pub"
    if ssh_key.exists():
        rows.append(("SSH Key", f"[green]✓[/green] [dim]{truncate(str(ssh_key), content_width() - 4)}[/dim]"))
    else:
        rows.append(("SSH Key", "[dim]not found[/dim]"))

    ssh_test = run_cmd("ssh -o StrictHostKeyChecking=accept-new -T git@github.com 2>&1", timeout=5)
    if "successfully authenticated" in ssh_test.lower():
        user = ""
        for part in ssh_test.split():
            if part.endswith("!"):
                user = part.rstrip("!")
                break
        rows.append(("GitHub SSH", f"[green]✓[/green] {user}" if user else "[green]✓[/green]"))
    else:
        rows.append(("GitHub SSH", "[dim]not connected[/dim]"))

    cred = run_cmd("git config --global credential.helper")
    if cred:
        rows.append(("Credentials", f"[green]✓[/green] {cred}"))

    return rows


# ---------------------------------------------------------------------------
# Git setup wizard helpers
# ---------------------------------------------------------------------------


def _git_install_gh() -> tuple[bool, str]:
    check = run_cmd("command -v gh", timeout=2)
    if check and "gh" in check:
        ver = run_cmd("gh --version | head -1", timeout=3)
        return True, ver or "installed"

    def _do_install() -> str:
        install_cmd = (
            "sudo mkdir -p -m 755 /etc/apt/keyrings && "
            "curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg "
            "| sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null && "
            "sudo chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg && "
            'echo "deb [arch=$(dpkg --print-architecture) '
            "signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] "
            'https://cli.github.com/packages stable main" '
            "| sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null && "
            "sudo apt-get update -qq && "
            "sudo apt-get install -y -qq gh"
        )
        return run_cmd(install_cmd, timeout=120)

    spinner_run("Installing gh CLI...", _do_install)

    check2 = run_cmd("command -v gh", timeout=2)
    if check2 and "gh" in check2:
        ver = run_cmd("gh --version | head -1", timeout=3)
        return True, ver or "installed"
    return False, "Installation failed"


def _git_setup_known_hosts() -> None:
    known_hosts = Path.home() / ".ssh" / "known_hosts"
    known_hosts.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = known_hosts.read_text(encoding="utf-8") if known_hosts.exists() else ""
    except OSError:
        existing = ""
    if "github.com" not in existing:
        run_cmd("ssh-keyscan -t ed25519 github.com >> ~/.ssh/known_hosts 2>/dev/null", timeout=10)


def _git_wizard_start(state: TuiState, user_input: str) -> CommandResult:
    print_step(1, 3, "GitHub Setup")

    ok, ver_or_err = _git_install_gh()
    if not ok:
        print_error(ver_or_err)
        return CommandResult(ok=False, style="silent")

    print_success(f"gh CLI [dim]{ver_or_err}[/dim]")

    _git_setup_known_hosts()

    auth_check = run_cmd("gh auth status 2>&1", timeout=5)
    if "Logged in" in auth_check:
        print_success("Already authenticated!")
        run_cmd("gh auth setup-git", timeout=5)
        print_success("Git credential helper configured")
        console.print()
        print_kv(_git_status_lines(), title="GitHub Status")
        return CommandResult(ok=True, style="silent", refresh=True)

    print_step(2, 3, "GitHub Setup")

    pad = content_pad()
    print_info("Create a Personal Access Token (classic):")
    console.print()
    console.print(f"{pad}[cyan bold]https://github.com/settings/tokens/new[/cyan bold]", highlight=False)
    console.print()
    console.print(
        f"{pad}[dim]Scopes:[/dim] [bold]repo[/bold], [bold]read:org[/bold], [bold]workflow[/bold]", highlight=False
    )
    console.print()

    return CommandResult(
        ok=True,
        style="silent",
        prompt="Token",
        pending_handler=_git_wizard_auth_token,
        wizard_step=(2, 3, "Token"),
    )


def _git_wizard_auth_token(state: TuiState, user_input: str) -> CommandResult:
    token = user_input.strip()
    if not token:
        print_error("Token must not be empty.")
        return CommandResult(
            ok=False,
            style="silent",
            prompt="Token",
            pending_handler=_git_wizard_auth_token,
            wizard_step=(2, 3, "Token"),
        )

    def _do_auth() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["gh", "auth", "login", "--with-token"],
            input=token,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )

    result = spinner_run("Authenticating...", _do_auth)
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()[:150]
        print_error(f"Failed: [dim]{err}[/dim]")
        console.print(f"{content_pad()}[dim]Check your token and try again.[/dim]", highlight=False)
        return CommandResult(
            ok=False,
            style="silent",
            prompt="Token",
            pending_handler=_git_wizard_auth_token,
            wizard_step=(2, 3, "Token"),
        )

    run_cmd("gh auth setup-git", timeout=5)

    auth_check = run_cmd("gh auth status 2>&1", timeout=5)
    account = parse_gh_account(auth_check)
    print_success(f"Logged in as [bold]{account}[/bold]" if account else "Authentication successful!")
    print_success("Git credential helper configured")

    ssh_key_path = Path.home() / ".ssh" / "id_ed25519.pub"
    if ssh_key_path.exists():
        print_step(3, 3, "GitHub Setup")
        pad = content_pad()
        print_info("SSH key found. Add it to GitHub?")
        console.print()
        console.print(f"{pad}[bold]y[/bold] [dim]Yes, add SSH key[/dim]", highlight=False)
        console.print(f"{pad}[bold]n[/bold] [dim]No, HTTPS only (usually sufficient)[/dim]", highlight=False)
        console.print()
        return CommandResult(
            ok=True,
            style="silent",
            prompt="SSH",
            pending_handler=_git_wizard_ssh_key,
            wizard_step=(3, 3, "SSH"),
        )

    print_success("HTTPS access configured")
    console.print()
    print_kv(_git_status_lines(), title="GitHub Status")
    return CommandResult(ok=True, style="silent", refresh=True)


def _git_wizard_ssh_key(state: TuiState, user_input: str) -> CommandResult:
    choice = user_input.strip().lower()
    if choice in ("y", "yes", "j", "ja"):
        hostname = socket.gethostname()

        def _do_add() -> str:
            title = shlex.quote(f"arasul@{hostname}")
            return run_cmd(
                f"gh ssh-key add ~/.ssh/id_ed25519.pub --title {title}",
                timeout=10,
            )

        result = spinner_run("Adding SSH key...", _do_add)

        if "error" in result.lower() or "failed" in result.lower():
            print_warning(f"SSH key upload issue: [dim]{result[:150]}[/dim]")
        elif "already" in result.lower() or not result:
            print_success("SSH key already registered on GitHub")
        else:
            print_success(f"SSH key added: [dim]arasul@{hostname}[/dim]")

        ssh_test = run_cmd("ssh -o StrictHostKeyChecking=accept-new -T git@github.com 2>&1", timeout=8)
        if "successfully authenticated" in ssh_test.lower():
            print_success("SSH connection to GitHub: OK")
        else:
            print_warning(f"SSH test: [dim]{ssh_test[:100]}[/dim]")

    elif choice in ("n", "no", "nein"):
        print_info("SSH skipped. HTTPS access is configured.")
    else:
        print_error("Please enter [bold]y[/bold] or [bold]n[/bold].")
        return CommandResult(
            ok=False,
            style="silent",
            prompt="SSH",
            pending_handler=_git_wizard_ssh_key,
            wizard_step=(3, 3, "SSH"),
        )

    console.print()
    print_success("[bold]GitHub setup complete![/bold]")
    console.print()
    print_kv(_git_status_lines(), title="GitHub Status")
    return CommandResult(ok=True, style="silent", refresh=True)


# ---------------------------------------------------------------------------
# /git (with subcommands: pull, push, log, status, or wizard)
# ---------------------------------------------------------------------------


def cmd_git(state: TuiState, args: list[str]) -> CommandResult:
    if not args:
        # No subcommand → GitHub setup wizard or status
        gh_check = run_cmd("gh auth status 2>&1", timeout=5)
        if "Logged in" in gh_check:
            print_kv(_git_status_lines(), title="GitHub Status")
            return CommandResult(ok=True, style="silent")
        return _git_wizard_start(state, "")

    sub = args[0].lower()

    # All subcommands require an active project
    if sub in ("pull", "push", "log", "status") and not state.active_project:
        print_warning("No active project.")
        return CommandResult(ok=False, style="silent")

    if sub == "pull":
        q = shlex.quote(str(state.active_project))
        output = run_cmd(f"git -C {q} pull 2>&1", timeout=30)
        if "Already up to date" in output:
            print_success("Already up to date.")
        elif "error" in output.lower() or "fatal" in output.lower():
            print_error(output[:200])
        else:
            print_success("Pulled latest changes.")
            if output:
                console.print(f"{content_pad()}[dim]{output[:200]}[/dim]", highlight=False)
        return CommandResult(ok=True, style="silent")

    if sub == "push":
        q = shlex.quote(str(state.active_project))
        output = run_cmd(f"git -C {q} push 2>&1", timeout=30)
        if "error" in output.lower() or "fatal" in output.lower():
            print_error(output[:200])
        else:
            print_success("Pushed to remote.")
        return CommandResult(ok=True, style="silent")

    if sub == "log":
        q = shlex.quote(str(state.active_project))
        output = run_cmd(f"git -C {q} log --oneline -10 2>/dev/null", timeout=5)
        if not output or output.startswith("Error"):
            print_info("No git history.")
        else:
            cw = content_width()
            rows: list[tuple[str, str]] = []
            for line in output.splitlines():
                parts = line.split(None, 1)
                if len(parts) == 2:
                    rows.append((f"[dim]{parts[0]}[/dim]", truncate(parts[1], cw - 10)))
                else:
                    rows.append((truncate(line, cw), ""))
            print_styled_panel("Recent Commits", rows)
        return CommandResult(ok=True, style="silent")

    if sub == "status":
        q = shlex.quote(str(state.active_project))
        output = run_cmd(f"git -C {q} status --short 2>/dev/null", timeout=5)
        if not output:
            print_success("Working tree clean.")
        else:
            pad = content_pad()
            console.print(f"{pad}[dim]{output}[/dim]", highlight=False, soft_wrap=True)
        return CommandResult(ok=True, style="silent")

    print_error(f"Unknown git subcommand: [bold]{sub}[/bold]")
    print_info("Available: [bold]pull[/bold], [bold]push[/bold], [bold]log[/bold], [bold]status[/bold]")
    return CommandResult(ok=False, style="silent")
