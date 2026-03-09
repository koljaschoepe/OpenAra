from __future__ import annotations

import contextlib
import os
import re
import tempfile
from pathlib import Path

from arasul_tui.core.claude_json import load_claude_json, save_claude_json

PROFILE = Path.home() / ".profile"
BASHRC = Path.home() / ".bashrc"
TOKEN_VAR = "CLAUDE_CODE_OAUTH_TOKEN"
TOKEN_PREFIX = "sk-ant-oat01-"

# Security note: The OAuth token is stored as a shell export in .profile/.bashrc
# because that is how Claude Code CLI reads it (via environment variable).
# File permissions are preserved (typically 0o644 for .bashrc, 0o644 for .profile).
# This is the same mechanism Claude Code uses natively.
_EXPORT_RE = re.compile(r'^export\s+CLAUDE_CODE_OAUTH_TOKEN=["\'].*["\']', re.MULTILINE)

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
        except (FileNotFoundError, PermissionError):
            continue
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith(f"export {TOKEN_VAR}="):
                raw_val = stripped.split("=", 1)[1].strip()
                # Strip inline comments (e.g. export VAR="value" # comment)
                if raw_val.startswith('"'):
                    # Quoted value — find closing quote
                    end = raw_val.find('"', 1)
                    val = raw_val[1:end] if end > 0 else raw_val.strip('"')
                elif raw_val.startswith("'"):
                    end = raw_val.find("'", 1)
                    val = raw_val[1:end] if end > 0 else raw_val.strip("'")
                else:
                    val = raw_val.split("#")[0].split()[0] if raw_val else ""
                if val.startswith(TOKEN_PREFIX):
                    return val
    return None


def _upsert_shell_export(path: Path, export_line: str, mode: int) -> None:
    """Insert or replace an export line in a shell config file."""
    try:
        text = path.read_text(encoding="utf-8")
        # Use existing permissions but ensure not world/group-readable (token safety)
        existing_mode = os.stat(path).st_mode & 0o7777
        mode = existing_mode & ~0o077  # strip group + other access
    except FileNotFoundError:
        text = ""
    except PermissionError:
        return  # Can't read the file — skip silently

    if _EXPORT_RE.search(text):
        text = _EXPORT_RE.sub(export_line, text)
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        text += f"\n{export_line}\n"

    # Atomic write: temp file + os.replace to prevent corruption on crash
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.chmod(tmp_path, mode)
        os.replace(tmp_path, str(path))
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


def _write_token(token: str) -> None:
    export_line = f'export {TOKEN_VAR}="{token}"'
    _upsert_shell_export(PROFILE, export_line, 0o600)
    _upsert_shell_export(BASHRC, export_line, 0o600)
    os.environ[TOKEN_VAR] = token


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
