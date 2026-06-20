# Open Ara — Agent Architecture

> Version: 0.6.0-draft · Stand: 2026-06-20

## Vision

Open Ara wird zu einem vollwertigen **lokalen Coding Agent** — Claude Code-Ersatz, der statt Anthropic-API das **Ollama-Modell auf dem Jetson AGX Orin** verwendet. Zielgruppe: Universitäten und Forschungseinrichtungen mit Air-Gap- oder Datenschutz-Anforderungen. Kein Code verlässt das Netz.

**Zwei Komponenten, klare Trennung:**

```
MacBook (Client)                    Jetson AGX Orin (Server)
━━━━━━━━━━━━━━━━━━━━━━━━━━━        ━━━━━━━━━━━━━━━━━━━━━━
Open Ara TUI  ←─────────────────── Ollama :11434/v1
  Agent Loop                          qwen3:14b (Q4)
  Tool Execution                      num_ctx 16384
  File I/O (lokal)
  Git-Ops (lokal)
```

Der Client enthält die gesamte Agent-Logik. Der Jetson ist ein **reiner Inference-Server** (OpenAI-kompatibler Endpunkt). Keine neuen Protokolle — Ollama's `/v1/chat/completions` mit Tool Calling.

---

## 1. Warum Python — und nicht TypeScript

Open Ara ist bereits Python (8.300 LOC, BUSL-1.1, 540 Tests). Die Entscheidung für TypeScript wäre ein Neustart.

Python-Vorteile für diesen Anwendungsfall:
- `openai` SDK: funktioniert 1:1 mit Ollama (gleiche API)
- `tree-sitter`: Repo-Map-Parsing für 40+ Sprachen
- `rich`: Streaming-Output, Diff-Panels, Live-Updates bereits integriert
- `prompt-toolkit`: Completion, History, Multi-line Input bereits vorhanden

---

## 2. Systemarchitektur

```
┌─────────────────────────────────────────────────────────────┐
│  MacBook — Open Ara TUI                                      │
│                                                              │
│  ┌──────────────┐    ┌─────────────────────────────────┐    │
│  │  TUI Shell   │    │  Agent Module (NEU)             │    │
│  │  (EXISTING)  │    │                                 │    │
│  │              │    │  ┌──────────┐  ┌─────────────┐  │    │
│  │  /project    │    │  │ Agent    │  │ Context Mgr │  │    │
│  │  /docker     │ ─▶ │  │ Loop     │  │ Repo Map    │  │    │
│  │  /git        │    │  │ (async)  │  │ Token Budget│  │    │
│  │  /system     │    │  └────┬─────┘  └─────────────┘  │    │
│  │  /agent  NEW │    │       │                          │    │
│  └──────────────┘    │  ┌────▼──────────────────────┐  │    │
│                      │  │ Tool Engine               │  │    │
│                      │  │ read · write · run · grep │  │    │
│                      │  │ Retry / Repair Logic      │  │    │
│                      │  └────┬──────────────────────┘  │    │
│                      │       │                          │    │
│                      │  ┌────▼──────────────────────┐  │    │
│                      │  │ Chat UI (Rich.Live)       │  │    │
│                      │  │ Diff Viewer + Approval    │  │    │
│                      │  └───────────────────────────┘  │    │
│                      └──────────────┬──────────────────┘    │
└─────────────────────────────────────┼────────────────────────┘
                                      │ HTTP (OpenAI-compat)
                                      ▼
┌─────────────────────────────────────────────────────────────┐
│  Jetson AGX Orin — arasul-platform                          │
│                                                              │
│  Ollama :11434                                               │
│  ├── qwen3:14b (Q4, 9.3 GB, tool-calling ✓)                 │
│  └── [zukünftig: qwen2.5-coder:14b, kleineres Routing-Modell]│
│                                                              │
│  Modelfile: num_ctx 16384, num_gpu_layers -1               │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Modul-Struktur (neu)

```
arasul_tui/
├── agent/                          # NEU — Agent-Kern
│   ├── __init__.py
│   ├── agent.py                    # Haupt-Agent-Loop (async)
│   ├── llm.py                      # LLM-Client (OpenAI-compat, Streaming, Retry)
│   ├── config.py                   # AgentConfig (model, base_url, context_limit)
│   ├── tools/
│   │   ├── __init__.py             # TOOL_DEFINITIONS Liste + Tool-Registry
│   │   ├── file_tools.py           # read_file, write_file, create_file
│   │   ├── shell_tools.py          # run_command (Sandbox, Timeout)
│   │   └── search_tools.py         # grep_files, find_files, list_files
│   ├── context/
│   │   ├── __init__.py
│   │   ├── repo_map.py             # tree-sitter Repo-Map
│   │   ├── budget.py               # Token-Budget-Manager
│   │   └── pruner.py               # Conversation-Pruning-Strategie
│   └── ui/
│       ├── __init__.py
│       ├── chat.py                 # Rich.Live Streaming-Chat-Panel
│       └── approval.py             # Diff-Viewer + Approve/Reject-Flow
│
└── commands/
    └── agent_cmd.py                # NEU: /agent Command → ruft agent.run() auf
```

**Neue Dependencies:**
```toml
[project.dependencies]
# bestehend
"prompt-toolkit>=3.0.0"
"rich>=13.0.0"
"psutil>=5.9.0"
"PyYAML>=6.0.0"

# neu
"openai>=1.50.0"          # LLM-Client (Ollama-kompatibel via base_url)
"tree-sitter>=0.23.0"     # Repo-Map-Parsing
"tree-sitter-python>=0.23.0"  # + weitere Sprachen nach Bedarf
"tiktoken>=0.7.0"         # Token-Counting (Fallback: len(text)/4)
```

---

## 4. Agent-Loop (Kernlogik)

```python
# arasul_tui/agent/agent.py

async def run_agent(task: str, state: TuiState, config: AgentConfig) -> None:
    project_path = state.active_project
    budget = TokenBudget(max_input=config.context_limit)   # z.B. 12_000
    repo_map = RepoMap(project_path)
    chat_ui = ChatUI(console)

    system_prompt = build_system_prompt(
        repo_map=repo_map.render(token_budget=2_048),
        project_path=project_path,
    )
    messages: list[dict] = [{"role": "user", "content": task}]

    async with chat_ui.session():
        while True:
            # 1. Context-Budget prüfen — ggf. Conversation kürzen
            if budget.estimate(messages) > budget.max * 0.85:
                messages = prune_conversation(messages, keep_last_n=6)

            # 2. LLM-Call mit Tools (Streaming)
            response = await llm_stream(
                messages=messages,
                system=system_prompt,
                tools=TOOL_DEFINITIONS,
                config=config,
                on_token=chat_ui.on_token,        # Live-Ausgabe
                on_tool_call=chat_ui.on_tool_call, # Tool-Progress
            )

            messages.append({"role": "assistant", **response.to_message()})

            # 3. Ende
            if response.stop_reason == "end_turn":
                break

            # 4. Tool Calls ausführen
            tool_results = []
            for tool_call in response.tool_calls:
                result = await _execute_tool_call(tool_call, project_path, chat_ui)
                tool_results.append(result)

            messages.append({"role": "tool", "content": tool_results})


async def _execute_tool_call(
    tool_call: ToolCall,
    project_path: Path,
    ui: ChatUI,
) -> ToolResult:
    # Destruktive Operationen → Approval
    if requires_approval(tool_call):
        diff = preview_tool_call(tool_call, project_path)
        approved = await ui.ask_approval(tool_call.name, diff)
        if not approved:
            return ToolResult(tool_call.id, "Action rejected by user.")

    # Ausführen mit Retry bei JSON-Parse-Fehlern
    for attempt in range(3):
        try:
            result = await TOOL_REGISTRY[tool_call.name](
                **tool_call.arguments,
                project_path=project_path,
            )
            return ToolResult(tool_call.id, result)
        except ToolExecutionError as e:
            if attempt == 2:
                return ToolResult(tool_call.id, f"Error after 3 attempts: {e}")
```

---

## 5. Context-Management — Das wichtigste Modul

### 5.1 Token-Budget

```
Gesamt-Context-Limit: 16.384 Tokens (Ollama Modelfile: num_ctx 16384)

Allocation:
├── System Prompt:        ~1.000 Tokens (fest)
├── Repo Map:             ~2.000 Tokens (komprimierbar)
├── Conversation History: ~6.000 Tokens (prunable)
├── Tool Results:         ~4.000 Tokens (letztes Tool-Call-Paar)
└── Reserve:              ~3.384 Tokens (Output-Buffer)
```

### 5.2 Repo-Map-Algorithmus

Angelehnt an Aider's Repo Map (MIT), portiert nach Python mit `tree-sitter`:

```python
def render(self, token_budget: int = 2_048) -> str:
    files = self._find_source_files()              # .py, .ts, .go, .rs, .java
    symbols = {f: self._extract_symbols(f) for f in files}

    # Sortierung: zuletzt modifiziert → wahrscheinlich relevant
    files_ranked = sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)

    output_lines = []
    tokens_used = 0
    for f in files_ranked:
        rel = f.relative_to(self.root)
        syms = symbols.get(f, [])
        line = f"  {rel}: {', '.join(syms[:8])}"  # max 8 Symbols pro Datei
        estimated = len(line) // 4
        if tokens_used + estimated > token_budget:
            break
        output_lines.append(line)
        tokens_used += estimated

    return "Repository:\n" + "\n".join(output_lines)
```

### 5.3 Conversation Pruning

Wenn der Context voll wird:
1. **Keep**: System Prompt + Repo Map (immer)
2. **Keep**: Erste User-Message (der ursprüngliche Task)
3. **Keep**: Letzte N Nachrichten (N=6, konfigurierbar)
4. **Drop**: Mittlere Nachrichten
5. **Summarize** (V2): Verdrängten Teil mit Mini-Call zusammenfassen

---

## 6. Tool-System

### Tool-Definitionen (OpenAI Function Calling Format)

```python
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file's content. Use start_line/end_line for large files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "start_line": {"type": "integer"},
                    "end_line": {"type": "integer"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write complete file content. Always shown as diff for approval.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run a shell command in the project directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "timeout": {"type": "integer", "default": 30},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Search for a pattern in source files (like grep -r).",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "file_pattern": {"type": "string", "default": "*"},
                    "case_sensitive": {"type": "boolean", "default": False},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files in a directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "default": "."},
                    "recursive": {"type": "boolean", "default": False},
                },
                "required": [],
            },
        },
    },
]
```

### Approval-Matrix

| Tool         | Approval nötig?        | Warum                              |
|--------------|------------------------|------------------------------------|
| `read_file`  | Nein                   | Read-only, nie destruktiv          |
| `list_files` | Nein                   | Read-only                          |
| `search_files` | Nein                 | Read-only                          |
| `write_file` | **Ja** (zeige Diff)    | Überschreibt Datei                 |
| `run_command` | **Ja** (bei rm/mv etc) | Kann destruktiv sein               |
| `run_command` | Nein (bei test/build) | Harmlose Commands pre-approved     |

**Safe-Command-Whitelist** (kein Approval nötig):
```python
SAFE_COMMANDS = {
    "python", "pytest", "npm test", "cargo test",
    "make", "cat", "echo", "git status", "git diff", "git log",
    "ls", "find", "grep", "rg",
}
```

---

## 7. Approval-Flow & Diff-UI

```
╔══════════════════════════════════════════════════════╗
║  write_file: src/auth.py                             ║
╠══════════════════════════════════════════════════════╣
║  - def login(user, password):                        ║
║  -     return check_db(user, password)               ║
║  + def login(user: str, password: str) -> bool:      ║
║  +     if not user or not password:                  ║
║  +         return False                              ║
║  +     return check_db(user, password)               ║
╚══════════════════════════════════════════════════════╝
  [y] Approve   [n] Reject   [e] Edit   [a] Approve All
```

Implementierung mit `rich.Panel` + `rich.Syntax` (Diff-Highlighting).

---

## 8. LLM-Client mit Retry

```python
# arasul_tui/agent/llm.py

async def llm_stream(
    messages: list[dict],
    system: str,
    tools: list[dict],
    config: AgentConfig,
    on_token: Callable[[str], None],
    on_tool_call: Callable[[ToolCall], None],
    max_retries: int = 3,
) -> LLMResponse:
    client = AsyncOpenAI(
        base_url=config.base_url,   # "http://jetson.local:11434/v1"
        api_key="ollama",           # Ollama ignoriert das, muss aber gesetzt sein
    )

    for attempt in range(max_retries):
        try:
            stream = await client.chat.completions.create(
                model=config.model,          # "qwen3:14b"
                messages=[{"role": "system", "content": system}, *messages],
                tools=tools,
                stream=True,
                temperature=0.1,             # niedrig für Code-Generierung
                max_tokens=4096,
            )

            response = LLMResponse()
            async for chunk in stream:
                # Text-Streaming
                if chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    on_token(token)
                    response.text += token

                # Tool-Call-Streaming
                if chunk.choices[0].delta.tool_calls:
                    response.accumulate_tool_calls(chunk.choices[0].delta.tool_calls)

            response.stop_reason = chunk.choices[0].finish_reason
            return response

        except json.JSONDecodeError:
            # Ollama hat ungültiges JSON für Tool-Call ausgegeben → Retry
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(0.5 * (attempt + 1))
```

---

## 9. Konfiguration

`~/.config/ara/config.yaml` (oder `.ara.yaml` im Projektordner):

```yaml
model:
  base_url: "http://jetson.local:11434/v1"  # Ollama-Endpunkt
  name: "qwen3:14b"
  context_limit: 12000                       # konservativ unter num_ctx 16384
  temperature: 0.1
  max_output_tokens: 4096

agent:
  approval_mode: "diff"           # diff | always | never
  safe_commands:                  # kein Approval für diese Prefixes
    - "pytest"
    - "npm test"
    - "cargo test"
    - "git "

ui:
  show_token_count: true
  streaming: true
```

**Fallback**: Wenn kein `base_url` konfiguriert, versucht Open Ara automatisch:
1. `http://localhost:11434/v1` (Ollama lokal)
2. `http://jetson.local:11434/v1` (mDNS)

---

## 10. Integration in bestehende TUI

### Neuer Command: `/agent`

```python
# arasul_tui/commands/agent_cmd.py

def cmd_agent(state: TuiState, args: list[str]) -> CommandResult:
    if not state.active_project:
        print_warning("No active project. Open one first.")
        return CommandResult(ok=False, style="silent")

    if args:
        # Direkter Task: /agent "fix the login bug"
        task = " ".join(args)
        asyncio.run(run_agent(task, state, load_config()))
        return CommandResult(ok=True, style="silent")

    # Kein Task → Multi-Line-Input-Mode
    return CommandResult(
        ok=True,
        style="silent",
        prompt="Task",
        pending_handler=_agent_task_handler,
    )
```

**Shortcut in der TUI:** `a` → sofort in Agent-Mode (analog zu `c` für Claude Code)

---

## 11. Roadmap V1 (6 Monate)

### Phase 1 — Core (Monat 1-2)
- [ ] `agent/llm.py`: OpenAI-Client, Streaming, Retry
- [ ] `agent/tools/`: read_file, write_file, run_command, search_files
- [ ] `agent/agent.py`: Basis-Loop ohne Context-Management
- [ ] `agent/ui/chat.py`: Rich.Live Streaming-Display
- [ ] `/agent`-Command in TUI integriert
- [ ] Manuelle Tests mit qwen3:14b auf Jetson

**Meilenstein:** "Ich kann `a 'fix the bug in auth.py'` tippen und der Agent liest, editiert, committed."

### Phase 2 — Context & Quality (Monat 3-4)
- [ ] `agent/context/repo_map.py`: tree-sitter Repo-Map
- [ ] `agent/context/budget.py`: Token-Budget-Manager
- [ ] `agent/context/pruner.py`: Conversation-Pruning
- [ ] `agent/ui/approval.py`: Diff-Viewer + Approve/Reject
- [ ] Tool-Retry-Logic für malformed JSON
- [ ] Config-System (`~/.config/ara/config.yaml`)
- [ ] `pytest`-Integration: Tests nach Änderungen automatisch ausführen

**Meilenstein:** "100-Datei-Repo funktioniert. Der Agent navigiert korrekt ohne Context-Overflow."

### Phase 3 — Produkt (Monat 5-6)
- [ ] Model-Selector in TUI (Modell wechseln ohne Restart)
- [ ] Session-Log (was hat der Agent getan — für Studenten auditierbar)
- [ ] Multi-User-Mode (Jetson-Queue-Manager für gleichzeitige Anfragen)
- [ ] Packaging: `pip install ara-agent` + Self-Update
- [ ] Uni-Features: Rate-Limiting pro User, Admin-Config
- [ ] CLAUDE.md-aware: Agent liest Projekt-CLAUDE.md automatisch

**Meilenstein:** "Erster zahlender Universitätskunde."

---

## 12. Kritische Risiken

| Risiko | Wahrscheinlichkeit | Mitigierung |
|--------|-------------------|-------------|
| qwen3:14b Tool-Call-Fehlerrate >30% | Mittel | Retry-Loop + Fallback zu simplerem Tool-Format |
| Context-Overflow bei großen Repos | Hoch | Repo-Map + aggressive Pruning |
| 60-100s Latenz frustriert Nutzer | Hoch | Sofortiges Streaming-Feedback, Token-Counter, klare UX |
| Ollama OOM bei Parallelnutzung | Mittel | Request-Queue auf Jetson-Seite, max 3 gleichzeitig |
| Diff-Anwendung korrumpiert Dateien | Niedrig | Immer Backup vor write_file, Git-Auto-Commit |

---

## 13. Was NICHT gebaut wird (Scope-Abgrenzung V1)

- Kein eigener Inference-Server (Ollama reicht)
- Kein Web-UI (TUI ist das Produkt)
- Kein IDE-Plugin (VS Code/JetBrains — das ist Continue.dev's Markt)
- Kein eigenes Modell-Training
- Keine Cloud-Komponente (das ist der Kernwert des Produkts)
- Kein Streaming-Audio / Voice-Interface (Jarvis hat das)

---

*Open Ara: lokale Intelligenz, keine Kompromisse bei Datenschutz.*
