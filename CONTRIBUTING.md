# Contributing to Arasul

Thank you for your interest in contributing! This project helps people set up Linux SBCs (Jetson, Raspberry Pi, and more) as headless development servers.

## How to Contribute

### Reporting Issues

- Use [GitHub Issues](https://github.com/koljaschoepe/OpenAra/issues) to report bugs or request features
- Include your platform (Jetson/RPi/other), OS version, and relevant log output
- Check existing issues before creating a new one

### Pull Requests

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Make your changes
4. Run tests: `pytest tests/`
5. Run linting: `ruff check .` and `ruff format --check .`
6. Run shellcheck on any modified shell scripts: `shellcheck -x --exclude=SC1091 scripts/*.sh setup.sh arasul_tui/install.sh lib/detect.sh lib/common.sh`
7. Commit with a clear message
8. Push and open a Pull Request

### Development Setup

```bash
git clone https://github.com/koljaschoepe/OpenAra.git
cd OpenAra
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/
```

### Code Style

- **Python**: Follows [ruff](https://docs.astral.sh/ruff/) defaults (configured in `pyproject.toml`)
- **Shell scripts**: Must pass [shellcheck](https://www.shellcheck.net/)
- **Commit messages**: Clear, concise, describe the "why" not just the "what"

### Shell Scripts

- All scripts must be idempotent (safe to run multiple times)
- Scripts should check prerequisites and skip completed steps
- Use `set -euo pipefail` at the top
- Log output goes to `/var/log/arasul/`

### Testing

- Tests are in `tests/` using pytest
- Run with: `pytest tests/ -v`
- CI enforces a **70% minimum coverage** threshold — PRs that drop below will fail
- New features should include tests where possible

### Areas Where Help Is Appreciated

- Support for additional SBC platforms (Orange Pi, Rock Pi)
- Translations of documentation
- Additional setup scripts for common use cases
- Improved error handling and recovery in setup scripts
- CI/CD improvements

## Code of Conduct

Be respectful and constructive. We're all here to make headless SBC development easier.
