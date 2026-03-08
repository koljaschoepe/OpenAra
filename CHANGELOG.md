# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.0] - 2026-03-07

### Added

- **Multi-platform support**: Arasul now runs on NVIDIA Jetson, Raspberry Pi 4/5, and generic Linux (aarch64/x86_64)
- **Hardware detection layer**: `lib/detect.sh` (shell) and `core/platform.py` (Python) auto-detect platform, storage, GPU, RAM
- **Storage auto-detection**: Best storage used automatically (NVMe > USB-SSD > SD card)
- **Interactive setup wizard**: `setup.sh` shows detected hardware and lets you select steps
- **Platform-adaptive TUI dashboard**: Shows GPU % on Jetson, CPU temp on RPi, generic fallback
- **Platform-specific aliases**: `config/aliases/common`, `config/aliases/jetson`, `config/aliases/raspberry_pi`
- **Platform-aware MOTD**: Login banner shows detected hardware
- **Platform-aware project templates**: GPU templates (`python-gpu`, `vision`) restricted to Jetson; `api`, `notebook`, `webapp` work everywhere
- **Shell tests**: `tests/test_detect_sh.py` for `lib/detect.sh` functions
- **Integration tests**: `tests/test_tui_integration.py` verifies TUI on non-Jetson platforms

### Changed

- **Repo renamed**: `jetson-dev-setup` → `arasul`
- **Config variables renamed**: `JETSON_USER` → `DEVICE_USER`, `NVME_MOUNT` → `STORAGE_MOUNT` (old names still work)
- **Script renamed**: `04-nvme-setup.sh` → `04-storage-setup.sh` (supports NVMe, USB-SSD, SD)
- **Config files renamed**: `99-jetson-*` → `99-arasul-*`
- **Prompt renamed**: `__jetson_ps1` → `__arasul_ps1`
- **All hardcoded `/mnt/nvme` paths** replaced with `platform.storage.mount`
- **Docker setup**: NVIDIA runtime only installed on Jetson
- **setup.sh**: Accepts all platforms (no longer exits on non-Jetson)
- **CI**: shellcheck covers `lib/detect.sh` + `lib/common.sh`, coverage threshold at 65%
- 501 tests, 70% coverage

### Backward Compatibility

- Old `.env` files with `JETSON_*` / `NVME_*` variables continue to work (auto-mapped)
- Existing Jetson workflows completely unchanged
- All 22 TUI commands work on all platforms (GPU commands gracefully degrade)

## [0.3.1] - 2026-03-07

### Changed

- **Architecture:** Split monolithic `ui.py` (707 lines) into `ui/` package with `output.py`, `panels.py`, `dashboard.py`
- **Architecture:** Resolved circular dependency between `meta.py` and `router.py` via state injection
- **Architecture:** Extracted `_dispatch_command()`, `_try_launch_shortcut()`, `_try_fuzzy_project()` from `app.py` run loop
- **Code quality:** Created `core/claude_json.py` — centralized `~/.claude.json` read/write (eliminated 14 duplicate patterns)
- **Code quality:** Extracted `_upsert_shell_export()` in `auth.py` (eliminated duplicated .profile/.bashrc logic)
- **Code quality:** Consolidated "no active project" guard in `git_ops.py` (4 identical checks → 1)
- **Code quality:** Added `is_pkg_installed`, `apt_install`, `mkdir_as_user`, `append_if_missing` helpers to `lib/common.sh`

### Fixed

- **Security:** Shell injection in `git_ops.py` — replaced `shell=True` with argument list for token auth
- **Security:** Path traversal protection in `project.py` with `_is_safe_name()` and `_validate_project_path()`
- **Security:** URL validation with regex in `project.py` (`_GIT_URL_RE`)
- **Security:** Input sanitization in `setup.sh` with `_sanitise()` function
- **Security:** Quoted `${NVME_DEVICE}` in heredoc cron in `04-nvme-setup.sh`
- **Robustness:** Narrowed `except Exception` to specific types in 10+ places (OSError, TimeoutExpired, etc.)
- **Robustness:** Fixed silent failure in `tailscale_cmd.py _do_down()` — now checks command output
- **Robustness:** Fixed false success on SSH key upload error in `git_ops.py`
- **Robustness:** Added error handling for `n8n_save_api_key()` in `n8n_cmd.py`
- **Robustness:** Wrapped `configure_mcp()` in try/except in `browser_cmd.py`
- **Robustness:** Added int-parse error check in `docker_info.py`

### Added

- 68 new tests (176 → 244), covering all previously untested command modules
- Test coverage reporting in CI with 55% minimum threshold
- Test files: `test_claude_json.py`, `test_shell.py`, `test_mcp_cmd.py`, `test_browser_cmd.py`, `test_tailscale_cmd.py`, `test_git_ops.py`, `test_system_cmd.py`, `test_ai_cmd.py`

*Versions 0.2.x and 0.4.x were internal development milestones (not released).*

## [0.1.0] - 2026-03-03

### Added

- Automated 8-step setup for Jetson Orin Nano Super (headless dev server)
- Arasul TUI with slash commands (/status, /open, /create, /clone, /claude, /codex, /git, /browser, /delete)
- UFW firewall (SSH + mDNS only)
- fail2ban with sshd + recidive jails
- Network hardening (SYN cookies, reverse-path filter)
- OOM protection for SSH and Docker
- Journald size/retention limits
- NVMe I/O scheduler optimization + weekly TRIM + health monitoring
- Headless Chromium via Playwright for AI agent browser automation
- Shared shell library (lib/common.sh)
- CI pipeline (ruff, shellcheck, pytest)
- Comprehensive test suite

### Security

- SSH key-only authentication with sshd config validation
- Automatic security updates via unattended-upgrades (Docker/NVIDIA excluded)
- fail2ban repeat offender protection (recidive jail)

### Fixed

- Shell injection vulnerability in TUI subprocess calls
- Venv path mismatch between installer and browser setup
- Missing STATIC_IP/STATIC_GATEWAY export in setup.sh
- Broken arasul-shell references (renamed to arasul)
- Binary existence check with incorrect shell=True usage
