from __future__ import annotations

import json
import shutil

from arasul_tui.core.auth import TOKEN_PREFIX, is_claude_configured, save_claude_auth
from arasul_tui.core.browser import ensure_browser
from arasul_tui.core.git_info import parse_gh_account
from arasul_tui.core.shell import run_cmd
from arasul_tui.core.state import TuiState
from arasul_tui.core.types import CommandResult
from arasul_tui.core.ui import (
    console,
    content_pad,
    print_error,
    print_info,
    print_step,
    print_styled_panel,
    print_success,
    print_warning,
)


def _launch_inline(state: TuiState, command: str) -> CommandResult:
    if not state.active_project:
        print_warning("No active project.")
        print_info("Open a project first — type its name or number on the main screen.")
        return CommandResult(ok=False, style="silent")
    if not shutil.which(command):
        print_error(f"[bold]{command}[/bold] is not installed.")
        print_info("Install: [bold]npm install -g @anthropic-ai/claude-code[/bold]")
        print_info("Or run [bold]/setup[/bold] → Step 6 (dev tools)")
        return CommandResult(ok=False, style="silent")
    print_info(f"Starting [bold]{command}[/bold] in [dim]{state.active_project.name}[/dim] ...")
    return CommandResult(
        ok=True,
        style="silent",
        quit_app=True,
        launch_command=command,
        launch_cwd=state.active_project,
    )


# ---------------------------------------------------------------------------
# Claude OAuth Setup Wizard
# ---------------------------------------------------------------------------


def _wizard_step_token(state: TuiState, user_input: str) -> CommandResult:
    token = user_input.strip()
    if not token.startswith(TOKEN_PREFIX):
        print_error(f"Token must start with [bold]{TOKEN_PREFIX}...[/bold]")
        return CommandResult(
            ok=False,
            style="silent",
            prompt="Token",
            pending_handler=_wizard_step_token,
            wizard_step=(1, 2, "Token"),
        )
    state._wizard_token = token
    print_success("Token accepted.")
    console.print()

    print_step(2, 2, "Claude Setup")

    pad = content_pad()
    print_info("Now paste your account info (JSON or UUID).")
    console.print()
    console.print(f"{pad}[dim]Run this on your Mac:[/dim]", highlight=False)
    cmd = "cat ~/.claude.json | python3 -c \"import json,sys; print(json.dumps(json.load(sys.stdin).get('oauthAccount',{})))\""
    console.print(f"{pad}  [cyan]{cmd}[/cyan]", highlight=False, soft_wrap=True)
    console.print()

    return CommandResult(
        ok=True,
        style="silent",
        prompt="JSON/UUID",
        pending_handler=_wizard_step_account_info,
        wizard_step=(2, 2, "Account"),
    )


def _wizard_step_account_info(state: TuiState, user_input: str) -> CommandResult:
    raw = user_input.strip()

    if raw.startswith("{"):
        try:
            data = json.loads(raw)
            uuid_val = data.get("accountUuid", "")
            email_val = data.get("emailAddress", "")
            if not uuid_val or "@" in uuid_val:
                print_error("JSON does not contain a valid accountUuid.")
                return CommandResult(
                    ok=False,
                    style="silent",
                    prompt="JSON/UUID",
                    pending_handler=_wizard_step_account_info,
                    wizard_step=(2, 2, "Account"),
                )
            if not email_val or "@" not in email_val:
                print_error("JSON does not contain a valid emailAddress.")
                return CommandResult(
                    ok=False,
                    style="silent",
                    prompt="JSON/UUID",
                    pending_handler=_wizard_step_account_info,
                    wizard_step=(2, 2, "Account"),
                )
            if not state._wizard_token:
                print_error("Token missing. Please restart the auth wizard.")
                return CommandResult(ok=False, style="silent")
            save_claude_auth(state._wizard_token, uuid_val, email_val)
            console.print()
            print_success(f"Account: [bold]{email_val}[/bold]")
            print_success("Claude Code is configured!")
            console.print()
            print_info("Type [bold]claude[/bold] to start coding.")
            return CommandResult(ok=True, style="silent", refresh=True)
        except Exception:
            print_error("Invalid JSON. Please paste the full output.")
            return CommandResult(
                ok=False,
                style="silent",
                prompt="JSON/UUID",
                pending_handler=_wizard_step_account_info,
                wizard_step=(2, 2, "Account"),
            )

    uuid = raw
    if "@" in uuid:
        print_error("That looks like an email, not a UUID.")
        print_info("The UUID looks like: [dim]xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx[/dim]")
        return CommandResult(
            ok=False,
            style="silent",
            prompt="UUID",
            pending_handler=_wizard_step_account_info,
            wizard_step=(2, 2, "Account"),
        )
    if len(uuid) < 8 or "-" not in uuid:
        print_error("Invalid UUID format.")
        print_info("Expected: [dim]xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx[/dim]")
        return CommandResult(
            ok=False,
            style="silent",
            prompt="UUID",
            pending_handler=_wizard_step_account_info,
            wizard_step=(2, 2, "Account"),
        )
    state._wizard_uuid = uuid
    print_success("UUID accepted.")
    console.print()
    print_info("Last step — your Claude/Anthropic email address:")
    return CommandResult(
        ok=True,
        style="silent",
        prompt="Email",
        pending_handler=_wizard_step_email,
        wizard_step=(2, 2, "Email"),
    )


def _wizard_step_email(state: TuiState, user_input: str) -> CommandResult:
    email = user_input.strip()
    if "@" not in email:
        print_error("That doesn't look like a valid email.")
        return CommandResult(
            ok=False,
            style="silent",
            prompt="Email",
            pending_handler=_wizard_step_email,
            wizard_step=(2, 2, "Email"),
        )
    if not state._wizard_token or not state._wizard_uuid:
        print_error("Auth state lost. Please restart the auth wizard.")
        return CommandResult(ok=False, style="silent")
    save_claude_auth(state._wizard_token, state._wizard_uuid, email)
    console.print()
    print_success("Claude Code is configured!")
    console.print()
    print_info("Type [bold]claude[/bold] to start coding.")
    return CommandResult(ok=True, style="silent", refresh=True)


def _auth_choice(state: TuiState, user_input: str) -> CommandResult:
    choice = user_input.strip()
    if choice == "1":
        print_step(1, 2, "Claude Setup")
        pad = content_pad()
        print_info("Get your OAuth token from your Mac:")
        console.print()
        console.print(f"{pad}  Run:   [cyan]claude setup-token[/cyan]", highlight=False)
        console.print(f"{pad}  Copy the token [dim](starts with sk-ant-oat01-...)[/dim]", highlight=False)
        console.print(f"{pad}  Paste it below.", highlight=False)
        console.print()
        return CommandResult(
            ok=True,
            style="silent",
            prompt="Token",
            pending_handler=_wizard_step_token,
            wizard_step=(1, 2, "Token"),
        )
    if choice == "2":
        ok, msg = ensure_browser()
        if not ok:
            print_error(msg)
            print_info("Install first with [bold]browser install[/bold].")
            return CommandResult(ok=False, style="silent")
        pad = content_pad()
        print_info("SSH tunnel method:")
        console.print()
        console.print(f"{pad}  [bold]1.[/bold] Open a new terminal on your Mac", highlight=False)
        console.print(f"{pad}  [bold]2.[/bold] Run:", highlight=False)
        console.print(f"{pad}     [cyan]ssh -L 1455:localhost:1455 mydevice[/cyan]", highlight=False)
        console.print(f"{pad}  [bold]3.[/bold] Then here: [cyan]claude login[/cyan]", highlight=False)
        console.print()
        return CommandResult(ok=True, style="silent")
    if choice == "3":
        pad = content_pad()
        print_info("Manual SSH tunnel:")
        console.print()
        console.print(f"{pad}  [bold]1.[/bold] Open a new terminal on your Mac", highlight=False)
        console.print(f"{pad}  [bold]2.[/bold] Run:", highlight=False)
        console.print(f"{pad}     [cyan]ssh -L 1455:localhost:1455 mydevice[/cyan]", highlight=False)
        console.print(f"{pad}  [bold]3.[/bold] On this device: [cyan]claude login[/cyan]", highlight=False)
        console.print()
        return CommandResult(ok=True, style="silent")
    print_error("Please choose [bold]1[/bold], [bold]2[/bold], or [bold]3[/bold].")
    return CommandResult(
        ok=False,
        style="silent",
        prompt="Method",
        pending_handler=_auth_choice,
        wizard_step=(1, 1, "Method"),
    )


# ---------------------------------------------------------------------------
# /claude
# ---------------------------------------------------------------------------


def cmd_claude(state: TuiState, _: list[str]) -> CommandResult:
    if not is_claude_configured():
        pad = content_pad()
        print_warning("Claude Code is not configured yet.")
        console.print()
        console.print(f"{pad}  [bold]1[/bold]  Enter token [dim](from setup-token on Mac)[/dim]", highlight=False)
        console.print(f"{pad}  [bold]2[/bold]  SSH tunnel  [dim](browser login on Mac)[/dim]", highlight=False)
        console.print(f"{pad}  [bold]3[/bold]  Manual      [dim](step-by-step instructions)[/dim]", highlight=False)
        console.print()
        return CommandResult(
            ok=True,
            style="silent",
            prompt="Method",
            pending_handler=_auth_choice,
            wizard_step=(1, 1, "Method"),
        )
    return _launch_inline(state, "claude")


# ---------------------------------------------------------------------------
# /auth
# ---------------------------------------------------------------------------


def cmd_auth(state: TuiState, _: list[str]) -> CommandResult:
    """Show authentication status."""
    rows: list[tuple[str, str]] = []

    # Claude
    if is_claude_configured():
        rows.append(("Claude Code", "[green]✓[/green] configured"))
    else:
        rows.append(("Claude Code", "[yellow]not configured[/yellow] — type [bold]claude[/bold]"))

    # GitHub
    gh_auth = run_cmd("gh auth status 2>&1", timeout=5)
    if "Logged in" in gh_auth:
        account = parse_gh_account(gh_auth)
        rows.append(("GitHub", f"[green]✓[/green] {account}" if account else "[green]✓[/green] connected"))
    else:
        rows.append(("GitHub", "[dim]not connected[/dim] — type [bold]git[/bold]"))

    # Browser/MCP
    from arasul_tui.core.browser import ensure_browser, is_mcp_configured

    browser_ok, _ = ensure_browser()
    if browser_ok:
        mcp = "[green]✓[/green] MCP active" if is_mcp_configured() else "[yellow]no MCP[/yellow]"
        rows.append(("Browser", f"[green]✓[/green] installed, {mcp}"))
    else:
        rows.append(("Browser", "[dim]not installed[/dim] — type [bold]browser install[/bold]"))

    print_styled_panel("Auth & Tools", rows)
    return CommandResult(ok=True, style="silent")
