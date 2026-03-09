# Arasul — Claude Code Context

## What Is This Repo?
Automated setup scripts to turn any Linux SBC into a headless development server. Supports NVIDIA Jetson, Raspberry Pi, and generic Linux systems. Optimized for remote development via SSH + Claude Code.

## Supported Platforms

| Platform | Models | Arch | GPU | Min RAM |
|----------|--------|------|-----|---------|
| **NVIDIA Jetson** | Orin Nano/NX/AGX, Xavier, TX2 | aarch64 | CUDA (NVIDIA) | 4 GB |
| **Raspberry Pi** | Pi 4 Model B, Pi 5 | aarch64 | None (VideoCore ignored) | 4 GB |
| **Generic Linux** | Any x86_64 or aarch64 | x86_64/aarch64 | None | 4 GB |

## Architecture: Hardware Abstraction Layer

Two-layer platform detection:

### Shell Layer: `lib/detect.sh`
Sourced by all setup scripts. Provides: `detect_platform()`, `detect_model()`, `detect_arch()`, `detect_gpu_type()`, `detect_storage_device()`, `detect_storage_type()`, `detect_storage_mount()`, `detect_ram_mb()`, `has_docker()`, `has_nvidia_runtime()`.

### Python Layer: `arasul_tui/core/platform.py`
Singleton `Platform` dataclass with `GpuInfo` and `StorageInfo` sub-dataclasses. Initialized once at TUI startup via `get_platform()`. All TUI modules use `platform.storage.mount` instead of hardcoded paths.

### Detection Strategy
- **Jetson**: `/etc/nv_tegra_release` or `nvidia-l4t-core` package or Tegra device-tree
- **Raspberry Pi**: `/proc/device-tree/model` contains "Raspberry Pi"
- **Generic**: Fallback for any other Linux system
- **Storage**: NVMe > USB-SSD > SD card (auto-detected via `lsblk`)

## Key Constraints
- ARM64 SBCs: not all x86 packages/containers available
- Docker images must be `linux/arm64` or multi-arch on ARM devices
- GPU features (CUDA, `--runtime=nvidia`) only available on Jetson
- Storage auto-detected: NVMe, USB-SSD, or SD card (projects on best available)

## Security Configuration
- SSH: Key-only auth (`/etc/ssh/sshd_config.d/99-arasul-hardened.conf`)
- Firewall: UFW active, only SSH (22) + mDNS (5353) allowed
- fail2ban: sshd jail + recidive jail (repeat offenders 1 week ban)
- Automatic security patches via `unattended-upgrades`
- Network hardening: SYN cookies, reverse-path filter, no redirects

## Performance Tuning
- Kernel: `vm.swappiness=10`, `vfs_cache_pressure=50`, `dirty_ratio=10`, `min_free_kbytes=65536`
- OOM protection: SSH (`OOMScoreAdjust=-900`), Docker (`-500`)
- I/O scheduler: `none` (NVMe), `mq-deadline` (USB-SSD), `bfq` (SD)
- Journald: 200MB limit, 1 week retention

## Configuration
All device-specific variables are in `.env` (created from `.env.example`).
Scripts read variables via exported environment variables from `setup.sh`.
Old `JETSON_*` / `NVME_*` variable names are still supported for backward compatibility.

## Repo Structure
```
├── .env.example        # Configuration template (platform-generic)
├── pyproject.toml      # Python package definition (Arasul TUI)
├── CLAUDE.md           # This file
├── README.md           # Setup guide (multi-platform)
├── setup.sh            # Main orchestrator (interactive wizard + auto mode)
├── lib/
│   ├── common.sh       # Shared shell library (log, err, check_root, helpers)
│   └── detect.sh       # Hardware detection library (platform, storage, GPU)
├── arasul_tui/
│   ├── app.py          # TUI application (two-level navigation, dispatch)
│   ├── install.sh      # Installer (venv + launcher)
│   ├── commands/       # Command handlers (11 modules)
│   │   ├── __init__.py      # Re-exports all handlers
│   │   ├── project.py       # /open, /create, /clone, /delete, /info, /repos
│   │   ├── ai.py            # /claude, /auth
│   │   ├── system.py        # /status, /health, /setup, /docker
│   │   ├── security.py      # /keys, /logins, /security
│   │   ├── git_ops.py       # /git (pull/push/log/status + setup wizard)
│   │   ├── browser_cmd.py   # /browser (status/test/install/mcp)
│   │   ├── mcp.py           # /mcp (list/add/test/remove)
│   │   ├── n8n_cmd.py       # /n8n (smart flow: install/start/api-key/mcp)
│   │   ├── tailscale_cmd.py # /tailscale (status/install/up/down)
│   │   ├── expose_cmd.py    # /expose (Tailscale Funnel on/off/status)
│   │   └── meta.py          # /help, /exit, /welcome
│   └── core/
│       ├── auth.py          # Claude OAuth token management
│       ├── browser.py       # Playwright/headless browser management
│       ├── cache.py         # Shell command caching + parallel execution
│       ├── claude_json.py   # Shared ~/.claude.json read/write helpers
│       ├── constants.py     # Shared constants (CLAUDE_JSON path)
│       ├── docker_info.py   # Docker container listing
│       ├── git_info.py      # Git metadata (branch, dirty, language detection)
│       ├── n8n_client.py    # n8n API client (health, workflows, compose)
│       ├── n8n_mcp.py       # n8n MCP server configuration
│       ├── n8n_project.py   # n8n project scaffolding
│       ├── platform.py      # Hardware detection (Platform, GpuInfo, StorageInfo)
│       ├── projects.py      # YAML project registry CRUD
│       ├── registry.py      # Command registry (with categories + subcommands)
│       ├── router.py        # Command routing and dispatch
│       ├── security.py      # SSH keys, login history, security audit
│       ├── setup_wizard.py  # Setup step definitions + runner
│       ├── shell.py         # Subprocess helper (run_cmd)
│       ├── state.py         # TUI state (Screen enum, wizard dict)
│       ├── templates.py     # Project templates (python-gpu, api, notebook, webapp)
│       ├── theme.py         # Color/icon constants for Rich output
│       ├── types.py         # CommandResult and type definitions
│       └── ui/              # Rich UI package (split from monolithic ui.py)
│           ├── __init__.py          # Re-exports all public symbols
│           ├── output.py            # Console, print helpers, spinner
│           ├── panels.py            # Styled panels, checklists, progress, KV
│           ├── dashboard.py         # Logo, system metrics, headers, prompt
│           └── animated_install.py  # Live progress panels for long installs
├── tests/              # Pytest test suite (536 tests, 76% coverage)
├── scripts/
│   ├── 01-system-optimize.sh   # Disable GUI, services, tune kernel
│   ├── 02-network-setup.sh     # Hostname, mDNS, UFW firewall, optional Tailscale
│   ├── 03-ssh-harden.sh        # Key-only auth, fail2ban (sshd + recidive)
│   ├── 04-storage-setup.sh     # NVMe/USB-SSD/SD setup, mount, swap
│   ├── 05-docker-setup.sh      # Docker, NVIDIA Runtime (Jetson only), Compose
│   ├── 06-devtools-setup.sh    # Node.js, Python, Git, Claude Code
│   ├── 07-quality-of-life.sh   # tmux, aliases (platform-specific), MOTD
│   ├── 08-browser-setup.sh     # Playwright + headless Chromium
│   ├── 09-n8n-setup.sh         # n8n workflow automation (Docker stack)
│   └── 10-miniforge-setup.sh   # Miniforge3 (lazy install for templates)
├── config/
│   ├── tmux.conf               # tmux configuration
│   ├── aliases/                # Platform-specific shell aliases
│   │   ├── common              # Shared aliases (docker, git, tmux, arasul)
│   │   ├── jetson              # NVIDIA tools (gpu, powermode, tegrastats)
│   │   └── raspberry_pi        # RPi tools (vcgencmd, pinout)
│   ├── motd-arasul             # Platform-aware login banner
│   └── mac-ssh-config          # SSH config template for Mac
├── docs/
│   ├── hardware-setup.md      # Step 0: Flash OS, install storage, first boot
│   ├── ssh-setup.md           # SSH key setup guide for macOS
│   └── claude-code-tips.md    # Claude Code patterns for Arasul devices
├── .github/
│   └── workflows/
│       └── ci.yml              # CI (ruff, shellcheck, pytest with coverage)
└── plans/                      # Local planning docs (gitignored)
```

## Script Conventions
- All scripts are idempotent — safe to run multiple times
- Scripts check prerequisites and skip completed steps
- Each script can run standalone or via `setup.sh`
- Platform detected via `$PLATFORM` (from `lib/detect.sh`)
- Logs at `/var/log/arasul/`
- Exit codes: 0=success, 1=error, 2=skipped

## Arasul TUI
- Source code in `arasul_tui/`
- Install locally from the repo:
  - `pip install -e .`
  - `arasul`
- Optional installer:
  - `./arasul_tui/install.sh`
  - Start with `arasul` or alias `atui`
- Two-level navigation: Main Screen → Project Screen
- 24 slash commands across 10 categories:
  - **Projects:** `/open`, `/create`, `/clone`, `/delete`, `/info`, `/repos`
  - **Claude Code:** `/claude`, `/auth`
  - **Git:** `/git` (no args = setup wizard), `/git pull`, `/git push`, `/git log`, `/git status`
  - **System:** `/status`, `/health`, `/setup`, `/docker`
  - **Security:** `/keys`, `/logins`, `/security`
  - **Browser:** `/browser` (smart flow: status → install → test → MCP)
  - **MCP:** `/mcp list|add|test|remove`
  - **Services:** `/n8n` (smart flow: install → start → API key → MCP), `/n8n stop`
  - **Network:** `/tailscale status|install|up|down`, `/expose status|on|off`
  - **Meta:** `/help`, `/exit`, `/welcome`
- Keyboard shortcuts: `1-9` (select project), `n` (new), `d` (delete), `c` (Claude), `g` (lazygit), `b` (back)

## Project Templates
- `/create --type <template>` creates projects with conda environments
- Templates: `python-gpu` (Jetson only), `vision` (Jetson only), `api` (Jetson only), `notebook`, `webapp`
- GPU templates check for CUDA availability and refuse on non-Jetson platforms
- Miniforge3 installed lazily on first template use
- Per-project conda envs on storage mount (`<storage>/envs/<name>`)
- CLAUDE.md auto-generated per template with actual hardware context

## Headless Browser (Playwright)
- Playwright + Chromium headless for AI agent browser automation
- Browser cache on storage: `<storage-mount>/playwright-browsers`
- MCP server: Playwright MCP configured in `~/.claude.json`
- Claude Code can navigate web pages, take screenshots, fill forms
- Installation: `sudo ./setup.sh --step 8` or `/browser install` in the TUI

## Useful Commands
```bash
arasul                  # Start the TUI
docker compose up -d    # Start stack
```

## Development Workflow
1. SSH from workstation: `ssh mydevice` — TUI starts automatically
2. Select project by number (`1-9`) or name
3. Press `c` — Claude Code launches in the project directory

## Important Paths (platform-adaptive)
- `<storage-mount>/projects/` — All projects (symlinked to `~/projects`)
- `<storage-mount>/docker/` — Docker data root
- `<storage-mount>/playwright-browsers/` — Headless Chromium cache
- `<storage-mount>/envs/` — Conda environments
- `/var/log/arasul/` — Setup logs
- `/etc/ssh/sshd_config.d/99-arasul-hardened.conf` — SSH hardening
- `/etc/sysctl.d/99-arasul-system.conf` — Kernel parameters

## ARM64 Notes
- `docker buildx` for multi-arch builds
- npm packages with native addons need `build-essential` + `python3`
- PyTorch for Jetson: NVIDIA wheels, not PyPI
- CUDA (Jetson only) at `/usr/local/cuda-12.6/`, already in PATH

## Development Setup (MacBook → Jetson)

### Workflow
```
MacBook (development) ──push──> GitHub (CI) ──deploy──> Jetson (production)
         │                          │                         │
    Claude Code               ruff + shellcheck          Live testing
    Edit + commit             pytest (70% min)           arasul TUI
    Plan in docs/plans/       3 Python versions          ssh jetson
```

### Deploy to Jetson
```bash
# From MacBook: commit + push
git add . && git commit -m "..." && git push origin main

# On device: pull + install
ssh <hostname> "cd <storage-mount>/projects/OpenAra && git pull origin main && pip install -e ."
```

### Target Device
- Host: `ssh <hostname>.local` (User: configured in .env)
- Repo: `<storage-mount>/projects/OpenAra`
- Launcher: `/usr/local/bin/arasul`

## Claude Code Workflow Rules

### Plan Mode
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately
- Write detailed specs upfront to reduce ambiguity

### Task Management
1. Write plan to `tasks/todo.md` with checkable items
2. Check in before starting implementation
3. Mark items complete as you go
4. After corrections: update `tasks/lessons.md` with the pattern

### Verification Before Done
- Never mark a task complete without proving it works
- Run tests, check ruff, verify on Jetson if relevant
- Ask: "Would a staff engineer approve this?"

### Quality Standards
- Simplicity first: minimal code impact, no over-engineering
- Find root causes, no temporary fixes
- Only touch what's necessary to avoid introducing bugs
- For non-trivial changes: pause and ask "is there a more elegant way?"

### Bug Fixing
- When given a bug report: just fix it autonomously
- Point at logs, errors, failing tests — then resolve them
- Fix failing CI tests without being told how

### Known Issues Reference
- Full bug list: `docs/plans/ROADMAP-v1.0.md` (79 issues, 15 phases)
- Active tasks: `tasks/todo.md`
- Lessons learned: `tasks/lessons.md`
