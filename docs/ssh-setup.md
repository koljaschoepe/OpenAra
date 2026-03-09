# SSH Key Setup Guide

This guide helps you set up SSH key authentication from your workstation to your device.

## macOS / Linux

### 1. Generate an SSH Key

Open Terminal and run:

```bash
ssh-keygen -t ed25519
```

- Press Enter for the default path (`~/.ssh/id_ed25519`)
- Enter a passphrase (recommended) or press Enter for none

### 2. Copy Your Key to the Device

```bash
ssh-copy-id username@hostname.local
```

Replace `username` and `hostname` with your actual values. You'll be asked for your password one last time.

### 3. Test the Connection

```bash
ssh username@hostname.local
```

If it connects without asking for a password, you're set.

### 4. Set Up SSH Config (Recommended)

Create or edit `~/.ssh/config`:

```bash
mkdir -p ~/.ssh/sockets
nano ~/.ssh/config
```

Add this block (replace `dev`, `HOSTNAME`, and `USER` with your values):

```
Host dev
    HostName HOSTNAME.local
    User USER
    IdentityFile ~/.ssh/id_ed25519
    ControlMaster auto
    ControlPersist 60
    ControlPath ~/.ssh/sockets/%r@%h-%p
    ServerAliveInterval 30
    ServerAliveCountMax 3
```

Now you can connect with just:

```bash
ssh dev
```

See [`config/mac-ssh-config`](../config/mac-ssh-config) for a full template with port forwarding examples.

## Windows

### Option A: WSL (recommended)

Install [WSL](https://learn.microsoft.com/en-us/windows/wsl/install) and follow the macOS/Linux steps above inside WSL.

### Option B: PowerShell

```powershell
ssh-keygen -t ed25519
type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh username@hostname.local "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"
```

## Troubleshooting

**"Permission denied (publickey)"** — Your key wasn't copied. Run `ssh-copy-id` again.

**"Could not resolve hostname"** — mDNS may not be running yet. Use the IP address instead: `ssh username@192.168.1.x`. On Windows, `.local` addresses require Bonjour/mDNS support — install [Bonjour Print Services](https://support.apple.com/kb/DL999) or use the IP address.

**Connection drops** — Clear stale sockets: `rm -f ~/.ssh/sockets/*`
