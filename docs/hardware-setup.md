# Hardware Setup Guide

From factory-new device to running OpenAra — pick your platform below.

**Already have a fresh OS and SSH access?** Skip this and go to the [Quick Start](../README.md#quick-start).

| Platform | What you need | Time |
|----------|--------------|------|
| [NVIDIA Jetson](#nvidia-jetson) | Ubuntu PC for flashing, NVMe SSD, paper clip | ~45 min |
| [Raspberry Pi](#raspberry-pi) | Raspberry Pi Imager, microSD, optional NVMe | ~20 min |
| [Generic Linux](#generic-linux) | Ubuntu Server, SSH | ~15 min |

---

<details>
<summary><h2>NVIDIA Jetson</h2></summary>

### Two Machines, Clear Roles

| Machine | Role | When |
|---------|------|------|
| **Ubuntu PC** (x86_64) | Flashing, serial console, oem-config | Initial setup only |
| **Mac / Windows** (your workstation) | SSH access, daily development | After setup, permanently |

After the initial setup you **never need the Ubuntu PC again** — the Jetson runs headless and you work via SSH.

### What You Need

#### Hardware

| # | Component | Details |
|---|-----------|---------|
| 1 | Jetson Dev Kit | Orin Nano Super, Orin NX, AGX Orin, Xavier, or TX2 |
| 2 | NVMe M.2 2280 PCIe SSD | 256GB–2TB (e.g. Samsung 980 PRO, WD SN770) |
| 3 | USB-C cable | Must support **data** (not just charging!) |
| 4 | Ethernet cable | Cat5e or Cat6 |
| 5 | 19V DC power supply | Included with Dev Kit |
| 6 | Small Phillips screwdriver | #1, for SSD mounting screw |
| 7 | **Paper clip** (or tweezers) | For Recovery Mode — bridging 2 pins for 3 seconds |

#### Software on the Ubuntu Flash Host

| # | Software | Installation |
|---|---------|-------------|
| 1 | **NVIDIA SDK Manager** | Download the **.deb** from [developer.nvidia.com/sdk-manager](https://developer.nvidia.com/sdk-manager) |
| 2 | **screen** | `sudo apt install screen` (for serial console) |
| 3 | **NVIDIA Developer Account** | Free at [developer.nvidia.com](https://developer.nvidia.com) |

> **Important:** SDK Manager only runs on **Ubuntu x86_64** (20.04 or 22.04). Download the **.deb variant**, not the Docker image.

---

### Step 1: Install the NVMe SSD

> Before first power-on. The Jetson is off, no cables connected.

1. Unbox the Dev Kit — check contents: Jetson module (pre-mounted on carrier board), 19V power supply, Quick Start Guide
2. **Flip the carrier board upside down** — the M.2 Key-M slot is on the **bottom side**
3. Remove the mounting screw next to the M.2 slot (if present)
4. Insert the NVMe SSD at a **30-degree angle** into the slot (gold contacts first)
5. Gently press the SSD down until it lies flat
6. Secure with the screw — **don't overtighten!**
7. Flip the board back over — verify the Jetson module (large chip with heatsink) is seated firmly

---

### Step 2: Enter Recovery Mode

> Right after SSD installation. Do NOT connect the power supply yet.

The Jetson Orin Nano Dev Kit has **no physical buttons**. Instead, there's a **Button Header (J14)** — a small 12-pin header on the carrier board. You bridge two pins with a paper clip.

```
Button Header (J14) — Pin Layout:

     ┌──────────────────────────┐
     │  12  10   8   6   4   2  │
     │  11   9   7   5   3   1  │
     └──────────────────────────┘

  Pins 9+10 → Force Recovery Mode  ← YOU NEED THIS
  Pins 7+8  → Reset
  Pins 1+2  → Power On/Off
```

<details>
<summary>What works as a jumper?</summary>

The pins are only **2.54 mm apart** — any piece of metal that touches both pins works:

| Household item | How to use |
|----------------|------------|
| **Paper clip** (recommended) | Bend it so two ends are parallel. Touch both pins simultaneously. |
| **Metal tweezers** | Press metal tips onto both pins. |
| **Stripped wire end** | A short piece of wire, e.g. from an old charging cable. |

</details>

**Procedure — in exactly this order:**

1. Plug the **USB-C cable** into the Jetson (next to USB-A ports) → other end into **Ubuntu PC**
2. **Press paper clip onto Pins 9 and 10** — hold both pins and **keep holding**
3. **While holding:** plug in the **19V power supply**
4. **Wait 2–3 seconds**
5. **Remove the paper clip**

The Jetson enters Recovery Mode (no screen output, no fan spin — this is normal).

**Verify on the Ubuntu PC:**

```bash
lsusb | grep -i nvidia
# Expected: Bus 001 Device 023: ID 0955:7523 NVIDIA Corp. APX
```

If you don't see `NVIDIA Corp.`: check USB-C cable (data-capable?), try a different USB port (directly on mainboard, not hub), repeat the procedure.

> **Tip:** If the Jetson is already running and you need Recovery Mode again:
> ```bash
> sudo reboot --force forced-recovery
> ```

---

### Step 3: Flash JetPack to NVMe

> Jetson is in Recovery Mode. You are on the **Ubuntu PC**.

**Install SDK Manager** (if not already done):

```bash
cd ~/Downloads
sudo apt install ./sdkmanager_*_amd64.deb
# If dependencies are missing:
sudo apt --fix-broken install
```

**Start it:**

```bash
sdkmanager
```

Sign in with your NVIDIA Developer Account. Then walk through the 3 steps:

**SDK Manager Step 1 — Development Environment:**

| Setting | Value |
|---------|-------|
| Product Category | Jetson |
| Hardware Configuration | **Your Jetson model** |
| Target OS | **JetPack 6.x** (latest) |
| DeepStream | Uncheck (not needed) |

**SDK Manager Step 2 — Components:**

- **Jetson Linux** (BSP): Must be selected
- **Jetson Runtime Components**: Recommended
- **Jetson SDK Components** (CUDA, cuDNN, TensorRT): Optional (~5GB), recommended for AI/ML

**SDK Manager Step 3 — Flash Settings (CRITICAL):**

| Setting | Value |
|---------|-------|
| Flash Method | **Manual Setup** |
| Storage Device | **NVMe** — **not eMMC or SD Card!** |
| OEM Configuration | **Pre-Config** (user account created in SDK Manager) |

> **Warning:** SDK Manager defaults to eMMC/SD card. You must **explicitly select NVMe**. If the option isn't visible, select "Manual Setup" first.

Click **Flash**. Takes **10–30 minutes**. Do not disconnect USB or power.

When complete, the Jetson reboots from the NVMe SSD automatically.

---

### Step 4: First Boot via Serial Console

> The Jetson boots for the first time. Stay on the **Ubuntu PC** (or switch to Mac).

The **same USB-C cable** serves as serial console. Wait **1–3 minutes** for boot.

```bash
# Find serial device
ls /dev/ttyACM*            # Ubuntu: typically /dev/ttyACM0

# Connect
sudo screen /dev/ttyACM0 115200
```

<details>
<summary>macOS serial console</summary>

```bash
ls /dev/cu.usbmodem*
screen /dev/cu.usbmodem* 115200

# Alternative (no Homebrew needed):
sudo cu -l /dev/cu.usbmodem14101 -s 115200
```

</details>

> Press **Enter** after connecting to see the login prompt. To exit: `Ctrl+A` then `K`.

**Log in and verify network:**

```bash
ip addr show eth0 | grep "inet "
# Output e.g.: inet 192.168.1.42/24 ...
```

> Note the **IP address** — you'll need it for SSH.

**Clone repo and run setup:**

```bash
git clone https://github.com/koljaschoepe/OpenAra.git
cd OpenAra
sudo ./setup.sh
```

The setup wizard detects your hardware, asks a few questions, and configures everything (~15 minutes).

**Reboot:**

```bash
sudo reboot
```

Done — close the serial console, disconnect USB-C. The Jetson is now fully configured.

---

### Step 5: SSH from Your Workstation

> The Ubuntu flash host is no longer needed.

1. **Copy your SSH key:**
   ```bash
   ssh-copy-id -i ~/.ssh/id_ed25519.pub your-user@<ip-address>
   ```

   <details>
   <summary>Permission denied? (password login already disabled)</summary>

   Add the key manually via serial console:
   ```bash
   # On your workstation — copy the key:
   cat ~/.ssh/id_ed25519.pub

   # On the Jetson (via serial console) — paste it:
   mkdir -p ~/.ssh && chmod 700 ~/.ssh
   echo "PASTE-YOUR-KEY-HERE" >> ~/.ssh/authorized_keys
   chmod 600 ~/.ssh/authorized_keys
   ```

   </details>

2. **Set up SSH alias** (see [SSH key setup guide](ssh-setup.md) for full config):
   ```
   # Add to ~/.ssh/config:
   Host jetson
       HostName <hostname>.local
       User <your-user>
       IdentityFile ~/.ssh/id_ed25519
   ```

3. **Connect:**
   ```bash
   ssh jetson    # TUI starts automatically
   ```

</details>

---

<details>
<summary><h2>Raspberry Pi</h2></summary>

### What You Need

- Raspberry Pi 4 (4GB+) or Pi 5 (4GB+)
- microSD card (16GB+) for boot
- **Pi 5 recommended:** M.2 HAT+ with NVMe SSD
- **Pi 4 recommended:** USB 3.0 SSD (via USB-A)
- USB-C power supply (5V/3A for Pi 4, 5V/5A for Pi 5)
- Ethernet cable (recommended) or WiFi
- Another computer with [Raspberry Pi Imager](https://www.raspberrypi.com/software/)

---

### Step 1: Flash Raspberry Pi OS

1. Download and install [Raspberry Pi Imager](https://www.raspberrypi.com/software/)
2. Open Imager and select:
   - **Device:** Your Pi model
   - **OS:** Raspberry Pi OS Lite (64-bit) — headless, no desktop
   - **Storage:** Your microSD card
3. Click the **gear icon** (Ctrl+Shift+X) for advanced settings:
   - **Set hostname:** e.g., `dev`
   - **Enable SSH:** password or public-key
   - **Set username and password**
   - **Configure WiFi** (optional, Ethernet preferred)
   - **Set locale and timezone**
4. Click **Write** and wait for completion
5. Insert the microSD into the Pi and power on

---

### Step 2: Install NVMe SSD (optional)

**Pi 5 with M.2 HAT+:**

1. Power off the Pi
2. Attach the M.2 HAT+ to the Pi 5's PCIe connector ([official guide](https://www.raspberrypi.com/products/m2-hat-plus/))
3. Insert NVMe SSD into the M.2 slot, secure with standoff and screw
4. Power on — Pi boots from microSD, OpenAra auto-detects the NVMe

**Pi 4 with USB-SSD:**

Plug a USB 3.0 SSD into a blue USB 3.0 port. That's it — OpenAra auto-detects it.

---

### Step 3: First SSH Connection

Wait 1-2 minutes for the Pi to boot, then:

```bash
ssh your-user@dev.local        # if you set hostname to "dev"
ssh your-user@<ip-address>     # or use the IP
```

<details>
<summary>Can't find the Pi?</summary>

```bash
ping dev.local
# Or scan the network:
nmap -sn 192.168.1.0/24
```

Also check your router's admin page for connected devices.

</details>

---

### Step 4: Run OpenAra Setup

```bash
git clone https://github.com/koljaschoepe/OpenAra.git
cd OpenAra
sudo ./setup.sh
```

OpenAra auto-detects the best available storage (NVMe > USB-SSD > SD card).

</details>

---

<details>
<summary><h2>Generic Linux</h2></summary>

### What You Need

- Any x86_64 or aarch64 machine with Ubuntu 22.04+ (or Debian-based)
- 4GB+ RAM
- SSH access enabled

### Setup

1. Install Ubuntu Server (or any Debian-based distro)
2. Enable SSH:
   ```bash
   sudo apt update && sudo apt install -y openssh-server
   sudo systemctl enable --now ssh
   ```
3. From your workstation:
   ```bash
   ssh your-user@<ip-address>
   ```
4. Run OpenAra setup:
   ```bash
   git clone https://github.com/koljaschoepe/OpenAra.git
   cd OpenAra
   sudo ./setup.sh
   ```

</details>

---

## After Setup

Once `setup.sh` completes and the device reboots:

```bash
ssh mydevice                    # TUI starts automatically
3                               # Select project by number
c                               # Launch Claude Code
```

See the [SSH key setup guide](ssh-setup.md) for configuring key-based authentication from your workstation.

## Storage Recommendations

| Device | Best Storage | Good Alternative | Minimum |
|--------|-------------|-----------------|---------|
| **Jetson Orin** | NVMe (flash via SDK Manager) | USB 3.0 SSD | microSD |
| **Pi 5** | NVMe (M.2 HAT+) | USB 3.0 SSD | microSD |
| **Pi 4** | USB 3.0 SSD | — | microSD |
| **Generic** | NVMe / SSD | USB 3.0 SSD | Local disk |

OpenAra auto-detects storage: **NVMe > USB-SSD > SD/local disk**. Projects, Docker data, swap, and conda environments go on the fastest available.

---

<details>
<summary><h2>Troubleshooting</h2></summary>

### Jetson Flash Problems

| Problem | Solution |
|---------|----------|
| SDK Manager doesn't detect Jetson | Check USB-C cable (data, not just charging). Try different USB port directly on mainboard. `lsusb \| grep -i nvidia` must show NVIDIA. |
| NVMe not available as flash target | SSD installed correctly? Must be PCIe NVMe, not SATA M.2. Select "Manual Setup" in SDK Manager. |
| Flash aborts | Stable network? Enough disk space on host (~30GB)? Try again. |
| oem-config doesn't appear | Wait 60s. Press Enter. Correct serial device? `ls /dev/ttyACM*` |

### Jetson Boot Problems

| Problem | Solution |
|---------|----------|
| No video output after setup | Normal — headless mode. Use serial console or SSH. |
| Boot hangs | Check NVMe SSD contact. Connect serial console for boot logs. |
| Boots from SD instead of NVMe | Recovery Mode via pins 9+10 on J14, re-flash to NVMe. Remove SD card. |

### SSH Problems (all platforms)

| Problem | Solution |
|---------|----------|
| Connection refused | SSH running? `systemctl status sshd` (via serial console if needed) |
| Permission denied (publickey) | Key not registered. Add manually via serial console. |
| Locked out after hardening | Serial console: `sudo screen /dev/ttyACM0 115200`, fix SSH config. |
| `.local` not resolving | Device: `systemctl status avahi-daemon`. Mac: `sudo killall -HUP mDNSResponder` |

### Raspberry Pi Problems

| Problem | Solution |
|---------|----------|
| Pi doesn't boot from microSD | Re-flash with Pi Imager, try a different card |
| NVMe not detected on Pi 5 | Ensure M.2 HAT+ PCIe ribbon cable is properly seated |
| Can't SSH after first boot | Wait 2 min, check Ethernet, verify hostname/IP |

</details>
