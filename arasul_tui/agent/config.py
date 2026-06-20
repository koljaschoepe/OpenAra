from __future__ import annotations

from dataclasses import dataclass, field

from arasul_tui.core.config import CONFIG_FILE, _load, _save

_AGENT_KEY = "agent"

_DEFAULTS: dict = {
    "base_url": "http://localhost:11434/v1",
    "model": "qwen3:14b",
    "context_limit": 12000,
    "num_ctx": 16384,
    "temperature": 0.1,
    "max_output_tokens": 4096,
    "safe_command_prefixes": [
        "pytest", "python -m pytest",
        "npm test", "npm run test",
        "cargo test",
        "make test", "make build",
        "git status", "git diff", "git log",
        "cat ", "ls ", "find ", "grep ", "rg ",
        "echo ",
    ],
}


@dataclass
class AgentConfig:
    base_url: str = "http://localhost:11434/v1"
    model: str = "qwen3:14b"
    context_limit: int = 12000
    num_ctx: int = 16384
    temperature: float = 0.1
    max_output_tokens: int = 4096
    safe_command_prefixes: list[str] = field(default_factory=list)

    def is_safe_command(self, command: str) -> bool:
        cmd = command.strip()
        return any(cmd.startswith(prefix) for prefix in self.safe_command_prefixes)


def load_agent_config() -> AgentConfig:
    data = _load().get(_AGENT_KEY, {})
    merged = {**_DEFAULTS, **data}
    return AgentConfig(
        base_url=merged["base_url"],
        model=merged["model"],
        context_limit=merged["context_limit"],
        num_ctx=merged.get("num_ctx", 16384),
        temperature=merged["temperature"],
        max_output_tokens=merged["max_output_tokens"],
        safe_command_prefixes=merged["safe_command_prefixes"],
    )


def save_agent_config(cfg: AgentConfig) -> None:
    data = _load()
    data[_AGENT_KEY] = {
        "base_url": cfg.base_url,
        "model": cfg.model,
        "context_limit": cfg.context_limit,
        "num_ctx": cfg.num_ctx,
        "temperature": cfg.temperature,
        "max_output_tokens": cfg.max_output_tokens,
        "safe_command_prefixes": cfg.safe_command_prefixes,
    }
    _save(data)
