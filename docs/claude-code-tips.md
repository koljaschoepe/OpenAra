# Claude Code Tips for Arasul Devices

Useful Claude Code patterns and workflows for working on Arasul-managed devices (Jetson, Raspberry Pi, or generic Linux SBCs).

## Quick Start

```bash
ssh dev                       # SSH alias (see docs/ssh-setup.md)
t                             # tmux session (alias for: tmux attach -t dev || tmux new -s dev)
cd ~/projects/my-app
claude                        # Start Claude Code
```

## Useful Claude Code Prompts

### System Health Check
```
claude -p "Check this device: disk space, RAM, temperature, Docker status. Summarize any issues."
```

### Bootstrap New Project
```
claude -p "Create a Python project in ~/projects/PROJECTNAME with: pyproject.toml, src/ layout, Dockerfile optimized for ARM64, docker-compose.yml, .gitignore and README. Python 3.10."
```

### Docker Compose
```
claude -p "Create a docker-compose.yml for DESCRIPTION. Requirements: multi-arch images, max 2GB RAM per container, health checks."
```

## Agent Patterns

### 1. Persistent Dev Session
Claude Code in a tmux pane — survives SSH disconnects:
```bash
tmux new -s claude
claude
# Ctrl-a d to detach
# tmux attach -t claude to reattach
```

### 2. Multi-Project Workflow
tmux windows for different projects:
```bash
tmux new -s dev
cd ~/projects/project-a && claude   # Window 1
# Ctrl-a c (new window)
cd ~/projects/project-b && claude   # Window 2
# Ctrl-a n/p to switch
```

### 3. System Administration
```
claude -p "Sysadmin for this device. Check and optimize: disk usage, Docker cleanup, log rotation, swap, RAM-intensive services."
```

## Platform Notes for Claude Code

### All Platforms
- **Docker images must match architecture**: ARM64 SBCs need `linux/arm64` images
- **No GUI**: Everything is terminal-based
- Projects under `<storage-mount>/projects/`

### Jetson-Specific
- **8GB shared RAM**: Max 2-3 Docker containers simultaneously
- **CUDA 12.6**: GPU in Docker with `--runtime=nvidia`
- **PyTorch needs NVIDIA wheels**: `pip install torch` doesn't work directly

### Raspberry Pi
- **No CUDA**: GPU features unavailable
- **Pi 4 (4GB)**: Tight RAM — avoid Playwright, limit Docker containers
- **Pi 5 (8GB)**: Comfortable headroom for most workloads

## CLAUDE.md Template for Projects

```markdown
# Project Name

## What
Brief description.

## Architecture
- Runtime: Docker on <device> (ARM64)
- Storage: <storage-mount>/projects/this-project

## Commands
- Build: `docker compose build`
- Run: `docker compose up -d`
- Test: `docker compose exec app pytest`
- Logs: `docker compose logs -f`

## Constraints
- Max 2GB RAM per container
- ARM64 images only
- Prefer offline-capable (edge deployment)
```
