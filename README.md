# Arasul

[![CI](https://github.com/koljaschoepe/OpenAra/actions/workflows/ci.yml/badge.svg)](https://github.com/koljaschoepe/OpenAra/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)

> Turn any Linux SBC into a headless development server. Automated setup for SSH hardening, storage, Docker, dev tools, and an interactive TUI. Supports NVIDIA Jetson, Raspberry Pi, and generic Linux.

## What Is This?

Arasul automates the boring parts of turning a Raspberry Pi or Jetson into a remote development machine.

**Without Arasul:** Hours of manual setup — security hardening, storage config, Docker install, SSH keys, firewall rules...

**With Arasul:** One command. 30 minutes. Production-ready.

### Who Is This For?

- Solo developers wanting a dedicated dev server
- AI/ML researchers with Jetson GPUs
- Anyone who wants Claude Code on a headless machine

## Platform Support

| Platform | Models | Storage | GPU | Status |
|----------|--------|---------|-----|--------|
| **NVIDIA Jetson** | Orin Nano/NX/AGX, Xavier, TX2 | NVMe, USB-SSD, SD | CUDA | Full support |
| **Raspberry Pi** | Pi 4 (4GB+), Pi 5 | NVMe (M.2 HAT+), USB-SSD, SD | None | Full support |
| **Generic Linux** | Any aarch64 / x86_64 | Auto-detected | None | Basic support |

## Quick Start

### Prerequisites

- A Raspberry Pi 4/5 (4GB+ RAM) or NVIDIA Jetson
- microSD card with Raspberry Pi OS / JetPack installed
- Network connection (Ethernet recommended)
- An SSH key on your Mac/PC — [don't have one?](docs/ssh-setup.md)

### Install

```bash
# On the device (via SSH):
git clone https://github.com/koljaschoepe/OpenAra.git
cd arasul
sudo ./setup.sh
```

The setup wizard will:
1. Detect your hardware automatically
2. Ask 3 questions (username, hostname, project name)
3. Show an installation plan and let you confirm
4. Configure everything and reboot

```
╭─────────────────────────────────────╮
│  Arasul Setup Wizard                │
╰─────────────────────────────────────╯

[i] Detected: Raspberry Pi 5 Model B (aarch64, 8192 MB RAM)
[i] Storage:  NVMe (/dev/nvme0n1)

  Username for this device [pi]:
  Hostname [raspberrypi]: dev
  Project name [arasul]:

╭─────────────────────────────────────╮
│  Installation Plan                  │
╰─────────────────────────────────────╯

  ✓ Step 1: System optimization
  ✓ Step 2: Network (hostname, mDNS, firewall)
  ✓ Step 3: SSH hardening (key-only auth, fail2ban)
  ✓ Step 4: Storage setup (NVMe/SSD, swap)
  ✓ Step 5: Docker + Compose
  ✓ Step 6: Dev tools (Node.js, Python, Claude Code)
  ✓ Step 7: Quality of life (tmux, aliases, MOTD)
  ○ Step 8: Headless browser (Playwright + Chromium)
  ○ Step 9: n8n workflow automation

  Proceed? [Y/n/customize]:
```

### After Reboot

```bash
ssh dev.local
arasul    # Start the management TUI
```

## What You Get

| Feature | Details |
|---------|---------|
| **Storage** | Best available auto-mounted (NVMe > USB-SSD > SD), projects on fast storage |
| **Swap** | Sized to RAM, on fast storage |
| **Docker** | Data on fast storage, NVIDIA Runtime on Jetson |
| **SSH hardened** | Key-only auth, fail2ban, UFW firewall |
| **Dev tools** | Node.js 22, Python 3, Git, Claude Code CLI |
| **tmux + Aliases** | Persistent sessions, platform-specific shortcuts |
| **Arasul TUI** | Interactive system management via `arasul` |
| **Browser** | Playwright + headless Chromium (optional) |
| **Custom MOTD** | Platform-aware dashboard on login |

## Setup Options

```bash
# Interactive wizard (default)
sudo ./setup.sh

# Interactive .env configuration + wizard
sudo ./setup.sh --interactive

# Run all steps without wizard
sudo ./setup.sh --auto

# Run a single step
sudo ./setup.sh --step 4    # Storage setup only
sudo ./setup.sh --step 6    # Dev tools only
```

## Configuration

The setup wizard creates `.env` automatically. You can also create/edit it manually:

```bash
cp .env.example .env
nano .env
```

Only `CUSTOMER_NAME` and `DEVICE_USER` are required — everything else is auto-detected or has sensible defaults. Full template: [`.env.example`](.env.example)

## Arasul TUI

The interactive TUI for system management, project workflows, and AI tool integration.

```bash
arasul       # or alias: atui
```

| Command | Description |
|---------|-------------|
| `/help` | Show all commands |
| `/status` | System status dashboard |
| `/create` | Create new project (with optional `--type` template) |
| `/clone` | Clone a GitHub repo |
| `/open <name>` | Open/activate a project |
| `/claude` | Start Claude Code |
| `/git` | GitHub CLI setup wizard |
| `/browser` | Headless browser management |
| `/mcp` | MCP server management |
| `/n8n` | n8n workflow automation |
| `/tailscale` | Tailscale VPN management |
| `/security` | Security audit checklist |

Keyboard shortcuts: `1-9` select project, `n` new, `d` delete, `c` Claude, `g` lazygit, `b` back.

### Project Templates

Create projects with pre-configured environments:

```bash
/create my-api --type api          # FastAPI project (all platforms)
/create my-nb --type notebook      # Jupyter notebook (all platforms)
/create my-app --type webapp       # Web application (all platforms)
/create my-ml --type python-gpu    # GPU/CUDA project (Jetson only)
/create my-cv --type vision        # Computer vision (Jetson only)
```

## Platform-Specific Notes

### NVIDIA Jetson

- **GPU**: CUDA available in Docker via `--runtime=nvidia`
- **RAM**: 8GB shared between CPU and GPU — no desktop, minimize services
- **Storage**: NVMe recommended (flash directly to NVMe via SDK Manager)
- **Power modes**: Configurable via `POWER_MODE` in `.env`
- **Monitoring**: `jtop` for GPU/CPU/RAM dashboard, `tegrastats` for one-liner
- **TUI dashboard**: Shows GPU %, power mode, temperature

### Raspberry Pi

- **Pi 5**: NVMe via M.2 HAT+ for best performance, same experience as Jetson
- **Pi 4**: USB-SSD via adapter recommended, microSD for boot only
- **RAM**: 4GB tight (skip browser), 8GB comfortable
- **No CUDA**: GPU templates (`python-gpu`, `vision`) unavailable
- **TUI dashboard**: Shows CPU temp, throttle status, storage

### Generic Linux

- **Detection**: Falls back to hostname for model identification
- **Storage**: Auto-detects NVMe/USB drives, falls back to home directory
- **Useful for**: CI runners, x86 dev machines, cloud VMs

## Daily Workflow

```bash
# 1. Connect from workstation
ssh mydevice

# 2. Start tmux (or resume)
t

# 3. Navigate to project
p                           # cd ~/projects
cd my-project

# 4. Start Claude Code
claude
```

## Repository Structure

```
├── .env.example                # Configuration template
├── pyproject.toml              # Python package (Arasul TUI)
├── setup.sh                    # Main orchestrator (wizard + auto)
├── lib/
│   ├── common.sh               # Shared shell library
│   └── detect.sh               # Hardware detection library
├── arasul_tui/                 # Interactive TUI (Python)
│   ├── app.py                  # Application entry point
│   ├── commands/               # 11 command modules
│   └── core/                   # Platform, state, registry, UI
├── tests/                      # Pytest suite (501 tests, 70% coverage)
├── scripts/
│   ├── 01-system-optimize.sh   # Disable GUI, tune kernel
│   ├── 02-network-setup.sh     # Hostname, mDNS, firewall
│   ├── 03-ssh-harden.sh        # Key-only auth, fail2ban
│   ├── 04-storage-setup.sh     # NVMe/USB-SSD/SD, mount, swap
│   ├── 05-docker-setup.sh      # Docker + NVIDIA Runtime (Jetson)
│   ├── 06-devtools-setup.sh    # Node.js, Python, Git, Claude Code
│   ├── 07-quality-of-life.sh   # tmux, aliases, prompt
│   ├── 08-browser-setup.sh     # Playwright + Chromium
│   └── 09-n8n-setup.sh         # n8n workflow automation
├── config/
│   ├── tmux.conf               # tmux configuration
│   ├── aliases/                # Platform-specific aliases
│   └── mac-ssh-config          # SSH config template
└── .github/workflows/ci.yml   # CI (ruff, shellcheck, pytest)
```

## Security & Performance

### Security

| Measure | Details |
|---------|---------|
| **SSH Key-Only Auth** | Password login disabled, Ed25519 public key only |
| **fail2ban** | 3 failed attempts → 1h ban, repeat offenders → 1 week ban |
| **UFW Firewall** | Deny incoming (only SSH + mDNS allowed), allow outgoing |
| **Auto Security Updates** | Ubuntu `-security` patches applied automatically |
| **Network Hardening** | SYN cookies, reverse-path filter, no redirects |

### Performance

| Measure | Details |
|---------|---------|
| **Kernel Tuning** | `vm.swappiness=10`, `vfs_cache_pressure=50`, `dirty_ratio=10` |
| **OOM Protection** | SSH daemon and Docker protected from OOM killer |
| **I/O Optimization** | Scheduler tuned per storage type (NVMe/SSD/SD) |
| **Journald Limit** | Max 200MB logs, 1 week retention, compressed |
| **Service Minimization** | Desktop, print, WiFi disabled on headless |

## Glossary

| Term | Meaning |
|------|---------|
| **SSH** | Secure remote terminal access to your device |
| **NVMe** | Fast SSD storage (much faster than SD card) |
| **Docker** | Run apps in isolated containers |
| **MCP** | Model Context Protocol — lets Claude use external tools |
| **mDNS** | Makes `hostname.local` work on your local network |
| **fail2ban** | Blocks attackers after repeated failed login attempts |
| **TUI** | Text User Interface — the interactive `arasul` menu |
| **Swap** | Uses disk as extra RAM (slower but prevents crashes) |

## Troubleshooting

### SSH Issues

| Problem | Solution |
|---------|----------|
| Connection refused | Check: `systemctl status sshd` |
| Permission denied (publickey) | Copy key: `ssh-copy-id user@device` |
| `.local` not resolving | Check: `systemctl status avahi-daemon` |

### Storage Issues

| Problem | Solution |
|---------|----------|
| NVMe/SSD not detected | Check `lsblk`. NVMe must be PCIe, not SATA M.2 |
| Slow performance | Check health: `sudo nvme smart-log /dev/nvme0n1` or `smartctl` |

### Docker Issues

| Problem | Solution |
|---------|----------|
| Daemon won't start | Check `journalctl -u docker` |
| GPU not available (Jetson) | `--runtime=nvidia` flag set? |
| Out of storage | `docker system prune -af --volumes` |

### RAM Issues

| Problem | Solution |
|---------|----------|
| OOM kills | Check `free -h`. Add memory limits to containers (`--memory=2g`) |
| Process killed | Check `dmesg \| grep -i oom`. SSH/Docker are OOM-protected |

## Maintenance

Most maintenance runs automatically. For manual checks:

```bash
# System updates
sudo apt update && sudo apt upgrade -y

# Docker cleanup (also weekly cron)
docker system prune -af --volumes

# Storage health
sudo smartctl -a /dev/nvme0n1  # or /dev/sda for USB-SSD

# Swap status
swapon --show

# Firewall
sudo ufw status verbose

# fail2ban
sudo fail2ban-client status sshd
```

## Migrating from Jetson-Only Setup

If you used an earlier version with `JETSON_*` variables:

- Old `.env` variables (`JETSON_USER`, `NVME_MOUNT`, etc.) still work — mapped automatically
- `/mnt/nvme` paths continue to work if that's where your storage is mounted
- All existing commands and workflows unchanged
- Run `sudo ./setup.sh` to pick up new platform-aware improvements

## License

MIT — see [LICENSE](LICENSE) for details.
