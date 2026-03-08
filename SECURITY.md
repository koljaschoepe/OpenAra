# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 0.5.x   | :white_check_mark: |
| < 0.5   | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Do not** open a public GitHub issue for security vulnerabilities
2. Email **security@koljaschoepe.dev** with:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)
3. You will receive an acknowledgment within 48 hours
4. A fix will be developed and released as soon as possible

## Security Measures

This project implements the following security measures on the target device:

- **SSH**: Key-only authentication, password login disabled
- **Firewall**: UFW with deny-all incoming policy (only SSH + mDNS allowed)
- **fail2ban**: sshd jail (3 attempts → 1h ban) + recidive jail (repeat offenders → 1 week ban)
- **Automatic Updates**: Security patches via `unattended-upgrades` (Docker/NVIDIA excluded)
- **Network Hardening**: SYN cookies, reverse-path filtering, ICMP redirect rejection
- **OOM Protection**: SSH and Docker services protected from OOM killer
- **Subprocess Safety**: All shell calls in the TUI use `shlex.quote()` for input sanitization

## Scope

This security policy covers:

- The setup scripts (`setup.sh`, `scripts/*.sh`)
- The Arasul TUI (`arasul_tui/`)
- Configuration files (`config/`)

It does **not** cover vulnerabilities in upstream dependencies (Ubuntu, Docker, NVIDIA JetPack, Node.js, etc.). Please report those to the respective projects.
