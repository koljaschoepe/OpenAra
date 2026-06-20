"""Tool registry and OpenAI tool definitions for the Open Ara agent."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from arasul_tui.agent.tools._base import ToolError
from arasul_tui.agent.tools.file_tools import read_file, write_file
from arasul_tui.agent.tools.search_tools import list_files, search_files
from arasul_tui.agent.tools.shell_tools import run_command

__all__ = [
    "TOOL_DEFINITIONS",
    "DESTRUCTIVE_TOOLS",
    "execute_tool",
    "requires_approval",
    "ToolError",
]

# Tools that always require user approval before execution
DESTRUCTIVE_TOOLS: frozenset[str] = frozenset({"write_file"})

# run_command approval is context-dependent — see requires_approval()

_REGISTRY: dict[str, Any] = {
    "read_file": read_file,
    "write_file": write_file,
    "run_command": run_command,
    "search_files": search_files,
    "list_files": list_files,
}

TOOL_DEFINITIONS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read the contents of a file in the project. "
                "Use start_line and end_line to read specific sections of large files."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path relative to project root",
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "First line to read (1-based, inclusive)",
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "Last line to read (1-based, inclusive)",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "Write complete content to a file. Creates the file if it doesn't exist, "
                "or replaces its content. The user will see a diff and must approve. "
                "Always write the COMPLETE file content, not just the changed parts."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path relative to project root",
                    },
                    "content": {
                        "type": "string",
                        "description": "Complete file content to write",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": (
                "Run a shell command in the project directory. "
                "Use for running tests, builds, linters, git operations. "
                "Destructive commands (delete, overwrite) require approval."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to run",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default 30, max 120)",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": (
                "Search for a text pattern across source files (like grep -rn). "
                "Use this to find function definitions, usages, imports, etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Search pattern (regex supported)",
                    },
                    "file_pattern": {
                        "type": "string",
                        "description": "Glob pattern to filter files, e.g. '*.py' (default: '*')",
                    },
                    "case_sensitive": {
                        "type": "boolean",
                        "description": "Case-sensitive search (default: false)",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files and directories in the project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory to list (default: project root '.')",
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "List recursively (default: false)",
                    },
                },
                "required": [],
            },
        },
    },
]


async def execute_tool(
    name: str,
    arguments: dict[str, Any],
    project_path: Path,
) -> str:
    """Dispatch a validated tool call to its implementation.

    Returns a string result suitable for sending back to the LLM.
    Raises ToolError on expected failures; callers should catch and
    return the error message as a tool result so the agent can react.
    """
    fn = _REGISTRY.get(name)
    if fn is None:
        raise ToolError(f"Unknown tool: '{name}'. Available: {', '.join(_REGISTRY)}")
    return await fn(**arguments, project_path=project_path)


def requires_approval(tool_name: str, arguments: dict[str, Any]) -> bool:
    """Return True if this tool call must be shown to the user before running."""
    if tool_name in DESTRUCTIVE_TOOLS:
        return True
    if tool_name == "run_command":
        command = arguments.get("command", "").strip()
        # Approve anything that starts with a destructive verb or touches paths
        _DESTRUCTIVE_VERBS = (
            "rm ", "mv ", "cp ", "chmod ", "chown ", "truncate ",
            "git reset", "git clean", "git checkout --",
            "pip uninstall", "npm uninstall", "yarn remove",
        )
        return any(command.startswith(v) for v in _DESTRUCTIVE_VERBS)
    return False
