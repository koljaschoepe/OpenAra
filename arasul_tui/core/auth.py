from __future__ import annotations

import re
from pathlib import Path

from arasul_tui.core.claude_json import load_claude_json, save_claude_json

PROFILE = Path.home() / ".profile"
BASHRC = Path.home() / ".bashrc"
TOKEN_VAR = "CLAUDE_CODE_OAUTH_TOKEN"
TOKEN_PREFIX = "sk-ant-oat01-"
_EXPORT_RE = re.compile(r'^export\s+CLAUDE_CODE_OAUTH_TOKEN=".*"', re.MULTILINE)

# .profile is used for the token because .bashrc has a non-interactive guard
# that prevents env vars from loading in non-interactive SSH commands.
_TOKEN_FILES = [PROFILE, BASHRC]


def is_claude_configured() -> bool:
    return _has_token() and _has_account()


def save_claude_auth(token: str, account_uuid: str, email: str) -> None:
    _write_token(token)
    _write_account(account_uuid, email)


def get_auth_env() -> dict[str, str]:
    token = _read_token()
    if token:
        return {TOKEN_VAR: token}
    return {}


def _has_token() -> bool:
    return bool(_read_token())


def _read_token() -> str | None:
    for path in _TOKEN_FILES:
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            continue
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith(f"export {TOKEN_VAR}="):
                val = stripped.split("=", 1)[1].strip().strip('"').strip("'")
                if val.startswith(TOKEN_PREFIX):
                    return val
    return None


def _upsert_shell_export(path: Path, export_line: str, mode: int) -> None:
    """Insert or replace an export line in a shell config file."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        text = ""

    if _EXPORT_RE.search(text):
        text = _EXPORT_RE.sub(export_line, text)
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        text += f"\n{export_line}\n"

    path.write_text(text, encoding="utf-8")
    path.chmod(mode)


def _write_token(token: str) -> None:
    export_line = f'export {TOKEN_VAR}="{token}"'
    _upsert_shell_export(PROFILE, export_line, 0o600)
    _upsert_shell_export(BASHRC, export_line, 0o600)


def _has_account() -> bool:
    data = load_claude_json()
    acct = data.get("oauthAccount")
    return isinstance(acct, dict) and bool(acct.get("accountUuid"))


def _write_account(account_uuid: str, email: str) -> None:
    data = load_claude_json()
    data["oauthAccount"] = {
        "accountUuid": account_uuid,
        "emailAddress": email,
    }
    data["hasCompletedOnboarding"] = True
    save_claude_json(data)
