#!/usr/bin/env bash
# =============================================================================
# Hardware detection library for multi-platform support
# Source this file: source "$(dirname "$0")/../lib/detect.sh"
#
# Detects: platform type, model, architecture, GPU, storage, RAM
# Supports: Jetson (all), Raspberry Pi (4/5), generic Linux
# =============================================================================

# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

# Returns: "jetson" | "raspberry_pi" | "generic"
detect_platform() {
    # 1. Jetson: check Tegra release file or L4T package or device-tree
    if [[ -f /etc/nv_tegra_release ]]; then
        echo "jetson"
        return
    fi
    if dpkg -l nvidia-l4t-core 2>/dev/null | grep -q "^ii"; then
        echo "jetson"
        return
    fi
    if [[ -f /proc/device-tree/compatible ]] && grep -qi "tegra" /proc/device-tree/compatible 2>/dev/null; then
        echo "jetson"
        return
    fi

    # 2. Raspberry Pi: check device tree model
    if [[ -f /proc/device-tree/model ]] && grep -qi "raspberry pi" /proc/device-tree/model 2>/dev/null; then
        echo "raspberry_pi"
        return
    fi

    # 3. Fallback: generic Linux
    echo "generic"
}

# Returns full model string, e.g. "NVIDIA Jetson Orin Nano Super" or "Raspberry Pi 5 Model B Rev 1.0"
detect_model() {
    if [[ -f /proc/device-tree/model ]]; then
        # device-tree model may have trailing null byte
        tr -d '\0' < /proc/device-tree/model
        return
    fi
    # Fallback: use hostname or uname
    uname -n
}

# Returns: "aarch64" | "x86_64" | "armv7l" | ...
detect_arch() {
    uname -m
}

# ---------------------------------------------------------------------------
# Boot path detection (Bookworm+ vs older)
# ---------------------------------------------------------------------------

# Returns: "/boot/firmware" (Bookworm+) or "/boot" (older)
detect_boot_path() {
    if [[ -d /boot/firmware ]]; then
        echo "/boot/firmware"
    else
        echo "/boot"
    fi
}

# ---------------------------------------------------------------------------
# GPU detection
# ---------------------------------------------------------------------------

# Returns: "nvidia" | "none"
# (VideoCore on RPi is deliberately ignored per project requirements)
detect_gpu_type() {
    # Check for NVIDIA GPU via Tegra or nvidia-smi
    if [[ -f /etc/nv_tegra_release ]]; then
        echo "nvidia"
        return
    fi
    if command -v nvidia-smi &>/dev/null; then
        echo "nvidia"
        return
    fi
    echo "none"
}

# Boolean: has NVIDIA GPU? (exit 0 = true, 1 = false)
has_nvidia_gpu() {
    [[ "$(detect_gpu_type)" == "nvidia" ]]
}

# Returns CUDA version string or empty
detect_cuda_version() {
    if [[ -f /usr/local/cuda/version.json ]]; then
        python3 -c "import json; print(json.load(open('/usr/local/cuda/version.json'))['cuda']['version'])" 2>/dev/null && return
    fi
    if command -v nvcc &>/dev/null; then
        nvcc --version 2>/dev/null | sed -n 's/.*release \([0-9]*\.[0-9]*\).*/\1/p' && return
    fi
    echo ""
}

# ---------------------------------------------------------------------------
# RAM detection
# ---------------------------------------------------------------------------

# Returns total RAM in MB
detect_ram_mb() {
    awk '/^MemTotal:/ { printf "%d", $2 / 1024 }' /proc/meminfo
}

# ---------------------------------------------------------------------------
# Storage detection
# ---------------------------------------------------------------------------

# Returns best external storage device path, or empty if only root filesystem
# Priority: NVMe > USB SSD > empty (root filesystem)
detect_storage_device() {
    local device

    # Check for NVMe
    device=$(lsblk -dno PATH,TRAN 2>/dev/null | awk '$2=="nvme" { print $1; exit }')
    if [[ -n "$device" ]]; then
        echo "$device"
        return
    fi

    # Check for USB storage (likely SSD/HDD via USB adapter)
    device=$(lsblk -dno PATH,TRAN,TYPE 2>/dev/null | awk '$2=="usb" && $3=="disk" { print $1; exit }')
    if [[ -n "$device" ]]; then
        echo "$device"
        return
    fi

    # No external storage found
    echo ""
}

# Returns: "nvme" | "usb_ssd" | "sd_only"
detect_storage_type() {
    local device
    device=$(detect_storage_device)

    if [[ -z "$device" ]]; then
        echo "sd_only"
        return
    fi

    local transport
    transport=$(lsblk -dno TRAN "$device" 2>/dev/null)

    case "$transport" in
        nvme) echo "nvme" ;;
        usb)  echo "usb_ssd" ;;
        *)    echo "sd_only" ;;
    esac
}

# Returns the mount point for the detected storage, or a sensible default
# If STORAGE_MOUNT is set in environment, uses that.
detect_storage_mount() {
    # Honor explicit override
    if [[ -n "${STORAGE_MOUNT:-}" ]]; then
        echo "$STORAGE_MOUNT"
        return
    fi

    # Legacy variable support
    if [[ -n "${NVME_MOUNT:-}" ]]; then
        echo "$NVME_MOUNT"
        return
    fi

    local device
    device=$(detect_storage_device)

    if [[ -z "$device" ]]; then
        # No external storage — use home directory
        if [[ -n "${REAL_USER:-}" ]]; then
            getent passwd "$REAL_USER" | cut -d: -f6
        else
            echo "$HOME"
        fi
        return
    fi

    # Check if device (or a partition of it) is already mounted
    local mount_point
    mount_point=$(lsblk -nro MOUNTPOINT "$device" 2>/dev/null | grep -v '^$' | head -1)
    if [[ -n "$mount_point" ]] && [[ -d "$mount_point" ]]; then
        echo "$mount_point"
        return
    fi

    # Not mounted yet — return default mount point
    echo "/mnt/data"
}

# Boolean helpers
has_nvme() {
    [[ "$(detect_storage_type)" == "nvme" ]]
}

has_external_storage() {
    [[ -n "$(detect_storage_device)" ]]
}

has_docker() {
    command -v docker &>/dev/null
}

has_nvidia_runtime() {
    has_docker && docker info 2>/dev/null | grep -qi "nvidia"
}

# ---------------------------------------------------------------------------
# Summary (for interactive wizard display)
# ---------------------------------------------------------------------------

# Prints a formatted hardware summary
print_hardware_summary() {
    local model arch ram_mb gpu storage_type storage_device storage_mount

    # platform detected but only used for future wizard logic
    detect_platform >/dev/null
    model=$(detect_model)
    arch=$(detect_arch)
    ram_mb=$(detect_ram_mb)
    gpu=$(detect_gpu_type)
    storage_type=$(detect_storage_type)
    storage_device=$(detect_storage_device)
    storage_mount=$(detect_storage_mount)

    echo ""
    echo "  Hardware detected:"
    echo "     Device:  ${model}"
    echo "     RAM:     $((ram_mb / 1024)) GB (${ram_mb} MB)"
    echo "     Arch:    ${arch}"

    case "$storage_type" in
        nvme)
            echo "     Storage: NVMe (${storage_device})"
            ;;
        usb_ssd)
            echo "     Storage: USB SSD (${storage_device})"
            ;;
        sd_only)
            echo "     Storage: SD/eMMC only (root filesystem)"
            ;;
    esac

    if [[ "$gpu" == "nvidia" ]]; then
        local cuda
        cuda=$(detect_cuda_version)
        echo "     GPU:     NVIDIA (CUDA ${cuda:-unknown})"
    else
        echo "     GPU:     None"
    fi

    echo "     Mount:   ${storage_mount}"
    echo ""
}
