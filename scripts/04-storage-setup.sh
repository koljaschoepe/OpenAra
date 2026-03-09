#!/usr/bin/env bash
# =============================================================================
# 04 — Storage Setup (Multi-Platform)
# Supports NVMe, USB-SSD, and SD-only configurations.
# Partition, format, mount, swap, directory structure, I/O scheduler,
# TRIM, health monitoring, Docker cleanup cron
# =============================================================================
set -euo pipefail

# shellcheck source=../lib/common.sh
source "$(dirname "$0")/../lib/common.sh"

# shellcheck source=../lib/detect.sh
source "$(dirname "$0")/../lib/detect.sh"

# Defaults for standalone execution
REAL_USER="${REAL_USER:-$(logname 2>/dev/null || echo "${SUDO_USER:-$USER}")}"
REAL_HOME="${REAL_HOME:-$(get_real_home)}"

check_root
export DEBIAN_FRONTEND=noninteractive

# ---------------------------------------------------------------------------
# Swap sizing based on detected RAM
# ---------------------------------------------------------------------------
# Usage: setup_swap_ram_based "external" | "sd"
setup_swap_ram_based() {
    local mode="$1"  # "external" or "sd"
    local swap_file swap_size

    if [[ "$mode" == "sd" ]]; then
        swap_file="${REAL_HOME}/swapfile"
    else
        swap_file="${STORAGE_MOUNT}/swapfile"
    fi

    # Use SWAP_SIZE from .env if set, otherwise compute from RAM
    if [[ -n "${SWAP_SIZE:-}" ]] && [[ "$SWAP_SIZE" != "auto" ]]; then
        if [[ ! "$SWAP_SIZE" =~ ^[0-9]+G$ ]]; then
            err "SWAP_SIZE must be in format like '8G' (got: $SWAP_SIZE)"
            return 1
        fi
        swap_size="$SWAP_SIZE"
    else
        local ram_mb
        ram_mb=$(detect_ram_mb 2>/dev/null || echo 0)
        if (( ram_mb <= 2048 )); then
            swap_size="2G"
        elif (( ram_mb <= 4096 )); then
            swap_size="4G"
        elif (( ram_mb <= 8192 )); then
            swap_size="8G"
        else
            swap_size="16G"
        fi
        # SD cards: cap swap to avoid excessive wear
        if [[ "$mode" == "sd" ]] && [[ "${swap_size%G}" -gt 8 ]]; then
            swap_size="8G"
        fi
        log "Auto-sized swap: ${swap_size} (based on ${ram_mb} MB RAM)"
    fi

    # shellcheck disable=SC2153
    if [[ ! -f "$swap_file" ]]; then
        log "Creating ${swap_size} swap on ${mode} storage..."

        # Disable zram swap if present (Jetson default)
        if [[ "${PLATFORM:-}" == "jetson" ]]; then
            systemctl disable nvzramconfig 2>/dev/null || true
        fi

        # Create new swap FIRST (before disabling old — prevents OOM on 4GB devices)
        # fallocate is fastest but fails on some filesystems (Btrfs, XFS with reflink)
        fallocate -l "$swap_size" "$swap_file" 2>/dev/null || {
            local size_gb="${swap_size%G}"
            dd if=/dev/zero of="$swap_file" bs=1M count=$((size_gb * 1024)) status=progress
        }
        chmod 600 "$swap_file"
        mkswap "$swap_file"

        # Now deactivate old swap entries (not the system swap blindly)
        while IFS= read -r old_swap; do
            [[ "$old_swap" == "$swap_file" ]] && continue
            swapoff "$old_swap" 2>/dev/null || true
        done < <(swapon --show=NAME --noheadings 2>/dev/null)

        swapon "$swap_file"

        if ! grep -q "$swap_file" /etc/fstab; then
            echo "${swap_file}    none    swap    sw    0    0" >> /etc/fstab
        fi

        log "Swap created and activated: ${swap_size}"
    else
        if swapon --show | grep -q "$swap_file"; then
            skip "Swap already active (${swap_file})"
        else
            swapon "$swap_file"
            log "Swap reactivated (${swap_file})"
        fi
    fi
}

# ---------------------------------------------------------------------------
# Determine storage configuration
# ---------------------------------------------------------------------------
# Use exported vars from setup.sh, or auto-detect
STORAGE_DEVICE="${STORAGE_DEVICE:-$(detect_storage_device)}"
STORAGE_MOUNT="${STORAGE_MOUNT:-$(detect_storage_mount)}"
STORAGE_TYPE="${STORAGE_TYPE:-$(detect_storage_type)}"

# Default mount point for new installs
DEFAULT_MOUNT="/mnt/data"

# ---------------------------------------------------------------------------
# SD-only mode — minimal setup, no partitioning
# ---------------------------------------------------------------------------
if [[ -z "$STORAGE_DEVICE" ]] || [[ "$STORAGE_TYPE" == "sd_only" ]]; then
    info "No external storage detected — using SD/eMMC (root filesystem)"
    info "Projects will be stored under ${REAL_HOME}/projects"

    # Create project directories under home
    DIRS=(
        "${REAL_HOME}/projects"
        "${REAL_HOME}/docker"
        "${REAL_HOME}/backups"
    )

    for dir in "${DIRS[@]}"; do
        if [[ ! -d "$dir" ]]; then
            mkdir -p "$dir"
            chown "${REAL_USER}:${REAL_USER}" "$dir"
            log "Created: $dir"
        fi
    done

    # Swap based on RAM (smaller for SD to reduce wear)
    setup_swap_ram_based "sd"

    log "SD-only storage setup complete"
    log "  Projects: ${REAL_HOME}/projects"
    exit 0
fi

# ---------------------------------------------------------------------------
# External storage detected — validate device
# ---------------------------------------------------------------------------
if ! lsblk "$STORAGE_DEVICE" &>/dev/null; then
    err "Storage device not found: ${STORAGE_DEVICE}"
    err "Check that the device is connected and try again"
    exit 1
fi

# Ensure partitioning tools are available
for tool in parted mkfs.ext4 blkid; do
    if ! command -v "$tool" &>/dev/null; then
        log "Installing missing tool: ${tool}"
        apt-get install -y -qq parted e2fsprogs util-linux 2>/dev/null || true
        break
    fi
done

DEVICE_SIZE=$(lsblk -b -d -n -o SIZE "$STORAGE_DEVICE" | head -1)
DEVICE_SIZE_GB=$(( DEVICE_SIZE / 1073741824 ))
log "${STORAGE_TYPE^^} detected: ${DEVICE_SIZE_GB} GB at ${STORAGE_DEVICE}"

# ---------------------------------------------------------------------------
# Determine partition path
# ---------------------------------------------------------------------------
# NVMe and eMMC use "p1" suffix (e.g. /dev/nvme0n1p1, /dev/mmcblk0p1),
# others use "1" (e.g. /dev/sda1)
if [[ "$STORAGE_DEVICE" == /dev/nvme* ]] || [[ "$STORAGE_DEVICE" == /dev/mmcblk* ]]; then
    STORAGE_PART="${STORAGE_DEVICE}p1"
else
    STORAGE_PART="${STORAGE_DEVICE}1"
fi

# ---------------------------------------------------------------------------
# Determine mount point
# ---------------------------------------------------------------------------
# If STORAGE_MOUNT is already set and exists, use it; otherwise default to /mnt/data
if [[ -z "$STORAGE_MOUNT" ]] || [[ "$STORAGE_MOUNT" == "$REAL_HOME" ]]; then
    STORAGE_MOUNT="$DEFAULT_MOUNT"
fi

# ---------------------------------------------------------------------------
# Partition and format
# ---------------------------------------------------------------------------
if ! lsblk -f "$STORAGE_PART" &>/dev/null; then
    # Safety: refuse to wipe a device that already has other partitions
    existing_parts=$(lsblk -n -o NAME "$STORAGE_DEVICE" 2>/dev/null | tail -n +2 | sed 's/^[[:space:]]*//')
    if [[ -n "$existing_parts" ]]; then
        err "Device ${STORAGE_DEVICE} has existing partitions but ${STORAGE_PART} was not found:"
        lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINT "$STORAGE_DEVICE" >&2
        err "Refusing to auto-partition — manual intervention required"
        exit 1
    fi

    warn "Partitioning ${STORAGE_DEVICE} — ALL DATA WILL BE ERASED"
    if [[ "${AUTO_CONFIRM:-false}" != "true" ]]; then
        read -rp "Type 'YES' to confirm: " confirm
        if [[ "$confirm" != "YES" ]]; then
            err "Aborted by user"
            exit 1
        fi
    else
        echo "Auto-confirm enabled — proceeding in 5 seconds..."
        sleep 5
    fi

    parted -s "$STORAGE_DEVICE" mklabel gpt
    parted -s "$STORAGE_DEVICE" mkpart primary ext4 0% 100%

    partprobe "$STORAGE_DEVICE"
    udevadm settle --timeout=10

    FS_LABEL="arasul-data"
    mkfs.ext4 -L "$FS_LABEL" "$STORAGE_PART"
    log "Storage partitioned and formatted as ext4 (label: ${FS_LABEL})"
else
    FS_TYPE=$(lsblk -f -n -o FSTYPE "$STORAGE_PART" | head -1)
    if [[ "$FS_TYPE" == "ext4" ]]; then
        skip "Storage already partitioned (ext4)"
    else
        warn "Storage partition exists but filesystem is: ${FS_TYPE}"
        warn "Manual formatting required if desired"
    fi
fi

# ---------------------------------------------------------------------------
# Mount storage
# ---------------------------------------------------------------------------
mkdir -p "$STORAGE_MOUNT"

if ! mountpoint -q "$STORAGE_MOUNT"; then
    mount "$STORAGE_PART" "$STORAGE_MOUNT"
    log "Storage mounted: ${STORAGE_MOUNT}"
else
    skip "Storage already mounted at ${STORAGE_MOUNT}"
fi

# fstab entry (UUID-based for stability)
# Retry blkid a few times — filesystem may not be immediately visible after mkfs
STORAGE_UUID=""
for _ in 1 2 3; do
    STORAGE_UUID=$(blkid -s UUID -o value "$STORAGE_PART" 2>/dev/null || true)
    [[ -n "$STORAGE_UUID" ]] && break
    udevadm settle --timeout=5 2>/dev/null || true
    sleep 1
done
if [[ -z "$STORAGE_UUID" ]]; then
    err "Cannot determine filesystem UUID for ${STORAGE_PART}"
    exit 1
fi
if ! grep -q "$STORAGE_UUID" /etc/fstab 2>/dev/null; then
    # Remove old device-path-based entries
    sed -i "\|${STORAGE_PART}|d" /etc/fstab 2>/dev/null || true
    echo "UUID=${STORAGE_UUID}    ${STORAGE_MOUNT}    ext4    defaults,noatime    0    2" >> /etc/fstab
    log "fstab updated (UUID-based for stability)"
fi

chown "${REAL_USER}:${REAL_USER}" "$STORAGE_MOUNT"

# ---------------------------------------------------------------------------
# Backward-compatibility symlink: /mnt/nvme → /mnt/data
# ---------------------------------------------------------------------------
if [[ "$STORAGE_MOUNT" != "/mnt/nvme" ]] && [[ -d "/mnt/nvme" || -L "/mnt/nvme" ]]; then
    # Old /mnt/nvme exists — check if it's a real mount or already a symlink
    if mountpoint -q "/mnt/nvme" 2>/dev/null; then
        info "/mnt/nvme is a real mount — not creating symlink (migration not needed)"
    elif [[ -L "/mnt/nvme" ]]; then
        skip "Symlink /mnt/nvme already exists"
    fi
elif [[ "$STORAGE_MOUNT" == "/mnt/data" ]]; then
    # New install: create /mnt/nvme → /mnt/data symlink for backward compat
    if [[ ! -e "/mnt/nvme" ]]; then
        ln -sf "$STORAGE_MOUNT" /mnt/nvme
        log "Backward-compat symlink: /mnt/nvme → ${STORAGE_MOUNT}"
    fi
fi

# ---------------------------------------------------------------------------
# Directory structure
# ---------------------------------------------------------------------------
DIRS=(
    "${STORAGE_MOUNT}/projects"
    "${STORAGE_MOUNT}/docker"
    "${STORAGE_MOUNT}/models"
    "${STORAGE_MOUNT}/data"
    "${STORAGE_MOUNT}/backups"
    "${STORAGE_MOUNT}/tmp"
)

for dir in "${DIRS[@]}"; do
    if [[ ! -d "$dir" ]]; then
        mkdir -p "$dir"
        chown "${REAL_USER}:${REAL_USER}" "$dir"
        log "Created: $dir"
    fi
done

# ---------------------------------------------------------------------------
# Swap file on external storage
# ---------------------------------------------------------------------------
setup_swap_ram_based "external"

# ---------------------------------------------------------------------------
# I/O scheduler (per storage type)
# ---------------------------------------------------------------------------
DEVICE_NAME=$(basename "$STORAGE_DEVICE")
SCHEDULER_PATH="/sys/block/${DEVICE_NAME}/queue/scheduler"

if [[ -f "$SCHEDULER_PATH" ]]; then
    case "$STORAGE_TYPE" in
        nvme)
            echo none > "$SCHEDULER_PATH" 2>/dev/null || true
            log "I/O scheduler set to 'none' (NVMe)"
            ;;
        usb_ssd)
            echo mq-deadline > "$SCHEDULER_PATH" 2>/dev/null || true
            log "I/O scheduler set to 'mq-deadline' (USB-SSD)"
            ;;
        *)
            info "No I/O scheduler change for storage type: ${STORAGE_TYPE}"
            ;;
    esac
fi

# Persistent udev rule — covers both NVMe and USB-SSD on reboot
UDEV_RULE="/etc/udev/rules.d/60-storage-scheduler.rules"
if [[ ! -f "$UDEV_RULE" ]]; then
    cat > "$UDEV_RULE" << 'EOF'
# Arasul: I/O scheduler rules for storage devices
# NVMe: no scheduling needed (internal command queuing)
ACTION=="add|change", KERNEL=="nvme*", ATTR{queue/scheduler}="none"
# USB-SSD: mq-deadline for balanced latency
ACTION=="add|change", KERNEL=="sd[a-z]", ATTR{queue/rotational}=="0", ATTR{queue/scheduler}="mq-deadline"
EOF
    log "Persistent I/O scheduler udev rules installed"
else
    skip "I/O scheduler udev rules already set"
fi

# ---------------------------------------------------------------------------
# TRIM (only for devices that support it)
# ---------------------------------------------------------------------------
DISC_GRAN=$(lsblk -dno DISC-GRAN "$STORAGE_DEVICE" 2>/dev/null | tr -d ' ')
if [[ -n "$DISC_GRAN" ]] && [[ "$DISC_GRAN" != "0B" ]]; then
    systemctl enable --now fstrim.timer 2>/dev/null || true
    log "Weekly TRIM enabled (fstrim.timer) — device supports TRIM"
else
    info "TRIM not supported by ${STORAGE_DEVICE} — skipping"
fi

# ---------------------------------------------------------------------------
# Health monitoring cron (NVMe and SSDs with smartctl)
# ---------------------------------------------------------------------------
if command -v smartctl &>/dev/null; then
    HEALTH_CRON="/etc/cron.weekly/storage-health"
    if [[ ! -f "$HEALTH_CRON" ]]; then
        cat > "$HEALTH_CRON" << EOF
#!/bin/bash
smartctl -a "${STORAGE_DEVICE}" >> /var/log/arasul/storage-health.log 2>&1
EOF
        chmod +x "$HEALTH_CRON"
        log "Weekly storage health check cron installed"
    else
        skip "Storage health cron already exists"
    fi
else
    # Install smartmontools if NVMe (important for health monitoring)
    if [[ "$STORAGE_TYPE" == "nvme" ]]; then
        apt-get install -y smartmontools >/dev/null 2>&1 || true
        if command -v smartctl &>/dev/null; then
            HEALTH_CRON="/etc/cron.weekly/storage-health"
            cat > "$HEALTH_CRON" << EOF
#!/bin/bash
smartctl -a "${STORAGE_DEVICE}" >> /var/log/arasul/storage-health.log 2>&1
EOF
            chmod +x "$HEALTH_CRON"
            log "Weekly storage health check cron installed (smartmontools)"
        fi
    fi
fi

# Remove old NVMe-specific cron if it exists and we have the new one
if [[ -f "/etc/cron.weekly/nvme-health" ]] && [[ -f "/etc/cron.weekly/storage-health" ]]; then
    rm -f "/etc/cron.weekly/nvme-health"
    log "Replaced old nvme-health cron with storage-health"
fi

# ---------------------------------------------------------------------------
# Docker cleanup cron
# ---------------------------------------------------------------------------
DOCKER_CRON="/etc/cron.weekly/docker-cleanup"
if [[ ! -f "$DOCKER_CRON" ]]; then
    cat > "$DOCKER_CRON" << 'EOF'
#!/bin/bash
docker system prune -f 2>/dev/null || true
EOF
    chmod +x "$DOCKER_CRON"
    log "Weekly Docker cleanup cron installed"
else
    skip "Docker cleanup cron already exists"
fi

# ---------------------------------------------------------------------------
# Symlink ~/projects
# ---------------------------------------------------------------------------
LINK="${REAL_HOME}/projects"
if [[ ! -L "$LINK" ]]; then
    # If ~/projects is a real directory (not a symlink), back it up first
    if [[ -d "$LINK" ]]; then
        warn "$LINK exists as a directory — backing up to ${LINK}.bak"
        mv "$LINK" "${LINK}.bak"
    fi
    ln -sfn "${STORAGE_MOUNT}/projects" "$LINK"
    chown -h "${REAL_USER}:${REAL_USER}" "$LINK"
    log "Symlink: ~/projects → ${STORAGE_MOUNT}/projects"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
STORAGE_FREE=$(df -h "$STORAGE_MOUNT" | awk 'NR==2{print $4}')
SWAP_TOTAL=$(free -h | awk '/^Swap:/{print $2}')

log "Storage setup complete"
log "  Type:     ${STORAGE_TYPE}"
log "  Device:   ${STORAGE_DEVICE}"
log "  Mount:    ${STORAGE_MOUNT}"
log "  Free:     ${STORAGE_FREE}"
log "  Swap:     ${SWAP_TOTAL}"
log "  Projects: ~/projects → ${STORAGE_MOUNT}/projects"
