# Open Ara — Claude Code Context

## What Is This Repo?

Open Ara is a local Claude Code replacement for university and air-gap environments.
A Python TUI client (MacBook / Linux) points at Ollama running on a Jetson AGX Orin
or any remote GPU server. BUSL-1.1 licensed; sellable as a plug-and-play appliance.

## Architecture

```
MacBook / student laptop          Jetson AGX Orin (GPU server)
─────────────────────             ─────────────────────────────
ara (TUI)                ──────▶  Ollama (llm-service:11434)
  prompt-toolkit REPL               qwen3:14b (default)
  AgentSession                      qwen3:14b-q8 (high quality)
  RepoMap (7 languages)
  Tool dispatcher
  ChatUI (streaming)
```

## Package Layout

```
arasul_tui/
├── app.py              ← entry point (ara / openara / arasul)
├── core/               ← state, router, registry, theme, config
├── commands/           ← all slash commands incl. agent_cmd.py
└── agent/
    ├── agent.py        ← AgentSession, multi-turn loop
    ├── config.py       ← AgentConfig, load/save
    ├── llm.py          ← chat(), streaming, retry, check_connection
    ├── repo_map.py     ← symbol extraction + token budget
    ├── budget.py       ← TokenBudget, prune_conversation
    ├── tools/          ← read_file, write_file, undo_file, run_command, search_files, list_files
    └── ui/
        └── chat.py     ← ChatUI, streaming output, ask_approval
```

## Key Design Decisions

- **num_ctx 16384** passed via `extra_body` — no Modelfile changes needed.
- **think=False** appends `/no_think` to system prompt for Qwen3 fast mode.
- **Backups** in `.openara-backups/<rel_path>/<timestamp_ns>.bak` — undo via `agent undo`.
- **tools_override=[]** on AgentSession disables tool calling (used for `/commit`).
- **system_override** bypasses repo_map injection (used for `/review`, `/commit`, `/explain`).
- **CLAUDE.md** in project root is injected into system prompt (max 12k chars).

## Commands

| Command | Aliases | What It Does |
|---------|---------|-------------|
| `agent <task>` | `a` | Multi-turn agent session |
| `agent config` | — | Show / change model, URL, think, num-ctx |
| `agent check` | — | Test Ollama connection |
| `agent undo [path]` | — | Restore file from backup |
| `review` | `code review` | AI code review of git diff |
| `commit` | `git commit` | AI commit message for staged changes |
| `explain [path]` | `what is` | Explain file / architecture |

## Ollama Connection

Default URL: `http://localhost:11434/v1`

For MacBook → Jetson:
```bash
# Option A: SSH tunnel (no server config needed)
ssh -N -L 11434:172.30.0.78:11434 arasul@arasul.tail746d9b.ts.net &
ara
# agent config url http://localhost:11434/v1  (already the default)

# Option B: Direct (expose Ollama port in Docker compose, then use Tailscale IP)
# agent config url http://arasul.tail746d9b.ts.net:11434/v1
```

## Dev Setup

```bash
git clone git@github.com:koljaschoepe/OpenAra.git /tmp/openara
cd /tmp/openara
pip install -e ".[dev]"
python -m pytest tests/ -q     # 685+ tests
ara                             # launch TUI
```

## Conventions

- All file I/O goes through `safe_path()` — no path traversal.
- Atomic writes: `tempfile.mkstemp` + `os.replace()`.
- Approval prompt for every destructive tool call (`write_file`, `run_command` with rm/mv/…).
- Token budget: 12k limit, prune at 80%, keep first + last-6 + placeholder.
