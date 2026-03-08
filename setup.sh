#!/usr/bin/env bash
# =============================================================================
# Arasul — Automated Headless Dev Server Setup
# =============================================================================
# Usage: sudo ./setup.sh [--auto] [--skip-reboot] [--step N] [--interactive]
#
# Supports: Jetson (all), Raspberry Pi (4/5), generic Linux (aarch64/x86_64)
#
# Prerequisites:
#   1. Fresh Linux install (JetPack, Raspberry Pi OS, Ubuntu, etc.)
#   2. First-boot setup completed (user account created)
#   3. SSH access to the device
#   (No .env needed — the setup wizard creates one automatically)
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="/var/log/arasul"
SKIP_REBOOT=false
SKIP_SSH_HARDENING=false
SINGLE_STEP=""
AUTO=false

# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

# shellcheck source=lib/detect.sh
source "${SCRIPT_DIR}/lib/detect.sh"

# ---------------------------------------------------------------------------
# Setup wizard: generate .env with 3 questions + auto-detection
# ---------------------------------------------------------------------------
run_setup_wizard() {
    echo ""
    echo "╭─────────────────────────────────────╮"
    echo "│  Arasul Setup Wizard                │"
    echo "╰─────────────────────────────────────╯"
    echo ""

    # Hardware auto-detect
    local model arch ram_mb storage_dev storage_type storage_mount
    model=$(detect_model)
    arch=$(detect_arch)
    ram_mb=$(detect_ram_mb 2>/dev/null || echo "unknown")
    storage_dev=$(detect_storage_device)
    storage_type=$(detect_storage_type)
    storage_mount=$(detect_storage_mount)

    info "Detected: ${model} (${arch}, ${ram_mb} MB RAM)"
    case "$storage_type" in
        nvme)    info "Storage:  NVMe (${storage_dev})" ;;
        usb_ssd) info "Storage:  USB SSD (${storage_dev})" ;;
        sd_only) info "Storage:  SD/eMMC only (root filesystem)" ;;
    esac
    echo ""

    # Sanitise user input: strip characters that could break sed or shell quoting
    _sanitise() { printf '%s' "$1" | tr -d '|"\\`$\n'; }

    # Question 1: Username
    local current_user="${SUDO_USER:-$(whoami)}"
    read -rp "  Username for this device [${current_user}]: " device_user
    device_user="${device_user:-$current_user}"

    # Question 2: Hostname
    local current_hostname
    current_hostname=$(hostname)
    read -rp "  Hostname [${current_hostname}]: " device_hostname
    device_hostname="${device_hostname:-$current_hostname}"

    # Question 3: Project name (optional)
    read -rp "  Project name [arasul]: " customer_name
    customer_name="${customer_name:-arasul}"

    echo ""

    local env_file="${SCRIPT_DIR}/.env"

    # Protect existing .env from accidental overwrite
    if [[ -f "$env_file" ]]; then
        cp "$env_file" "${env_file}.bak.$(date +%s)"
        warn "Existing .env backed up"
    fi

    cp "${SCRIPT_DIR}/.env.example" "$env_file"
    chmod 600 "$env_file"

    sed -i "s|CUSTOMER_NAME=\"CHANGEME\"|CUSTOMER_NAME=\"$(_sanitise "$customer_name")\"|" "$env_file"
    sed -i "s|DEVICE_USER=\"CHANGEME\"|DEVICE_USER=\"$(_sanitise "$device_user")\"|" "$env_file"
    sed -i "s|DEVICE_HOSTNAME=\"dev\"|DEVICE_HOSTNAME=\"$(_sanitise "$device_hostname")\"|" "$env_file"

    # Fill in auto-detected storage
    if [[ -n "$storage_dev" ]]; then
        sed -i "s|STORAGE_DEVICE=\"\"|STORAGE_DEVICE=\"${storage_dev}\"|" "$env_file"
        sed -i "s|STORAGE_MOUNT=\"\"|STORAGE_MOUNT=\"${storage_mount}\"|" "$env_file"
    fi

    # Sensible swap default for low-RAM devices
    if [[ "$ram_mb" != "unknown" ]] && (( ram_mb <= 4096 )); then
        sed -i "s|SWAP_SIZE=\"32G\"|SWAP_SIZE=\"2G\"|" "$env_file"
    elif [[ "$ram_mb" != "unknown" ]] && (( ram_mb <= 8192 )); then
        sed -i "s|SWAP_SIZE=\"32G\"|SWAP_SIZE=\"16G\"|" "$env_file"
    fi

    log "Configuration saved to .env"
    echo ""
}

# ---------------------------------------------------------------------------
# Load configuration
# ---------------------------------------------------------------------------
load_config() {
    local env_file="${SCRIPT_DIR}/.env"

    if [[ ! -f "$env_file" ]]; then
        info "No configuration found — starting setup wizard..."
        run_setup_wizard
    fi

    # shellcheck source=/dev/null
    source "$env_file"

    # Backward compatibility: map old variable names to new ones
    DEVICE_USER="${DEVICE_USER:-${JETSON_USER:-}}"
    DEVICE_HOSTNAME="${DEVICE_HOSTNAME:-${JETSON_HOSTNAME:-}}"
    STORAGE_DEVICE="${STORAGE_DEVICE:-${NVME_DEVICE:-}}"
    STORAGE_MOUNT="${STORAGE_MOUNT:-${NVME_MOUNT:-}}"

    # Validate required fields
    local missing=false
    for var in CUSTOMER_NAME DEVICE_USER DEVICE_HOSTNAME; do
        if [[ "${!var:-}" == "CHANGEME" ]] || [[ -z "${!var:-}" ]]; then
            err "Variable $var is not configured in .env"
            missing=true
        fi
    done

    if [[ "$missing" == true ]]; then
        err "Please edit .env or delete it and re-run to start the wizard"
        exit 1
    fi

    # Auto-detect storage if not explicitly configured
    if [[ -z "$STORAGE_DEVICE" ]]; then
        STORAGE_DEVICE=$(detect_storage_device)
    fi
    if [[ -z "$STORAGE_MOUNT" ]]; then
        STORAGE_MOUNT=$(detect_storage_mount)
    fi
    STORAGE_TYPE=$(detect_storage_type)

    # Set defaults
    SWAP_SIZE="${SWAP_SIZE:-32G}"
    INSTALL_TAILSCALE="${INSTALL_TAILSCALE:-false}"
    NODE_VERSION="${NODE_VERSION:-22}"
    INSTALL_CLAUDE="${INSTALL_CLAUDE:-true}"
    INSTALL_OLLAMA="${INSTALL_OLLAMA:-false}"
    INSTALL_ARASUL_TUI="${INSTALL_ARASUL_TUI:-true}"
    INSTALL_N8N="${INSTALL_N8N:-false}"
    POWER_MODE="${POWER_MODE:-3}"
    DOCKER_LOG_MAX_SIZE="${DOCKER_LOG_MAX_SIZE:-10m}"
    DOCKER_LOG_MAX_FILES="${DOCKER_LOG_MAX_FILES:-3}"
    GIT_USER_NAME="${GIT_USER_NAME:-}"
    GIT_USER_EMAIL="${GIT_USER_EMAIL:-}"

    # Derived variables
    REAL_USER="$DEVICE_USER"
    REAL_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)

    # Legacy variable names (kept for user .env backward compat only)
    JETSON_USER="$DEVICE_USER"
    JETSON_HOSTNAME="$DEVICE_HOSTNAME"
}

# ---------------------------------------------------------------------------
# Interactive mode: generate .env
# ---------------------------------------------------------------------------
interactive_config() {
    echo ""
    echo -e "${CYAN}╔═══════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║  Arasul — Interactive Configuration               ║${NC}"
    echo -e "${CYAN}╚═══════════════════════════════════════════════════╝${NC}"
    echo ""

    local env_file="${SCRIPT_DIR}/.env"

    read -rp "Customer / Project name: " i_customer
    read -rp "Device username: " i_user
    read -rp "Hostname [dev]: " i_hostname
    i_hostname="${i_hostname:-dev}"
    read -rp "Swap size [32G]: " i_swap
    i_swap="${i_swap:-32G}"
    read -rp "Install Tailscale? (true/false) [false]: " i_tailscale
    i_tailscale="${i_tailscale:-false}"
    read -rp "Git name: " i_git_name
    read -rp "Git email: " i_git_email
    read -rp "Install Claude Code? (true/false) [true]: " i_claude
    i_claude="${i_claude:-true}"
    read -rp "Install Arasul TUI? (true/false) [true]: " i_tui
    i_tui="${i_tui:-true}"

    # Protect existing .env from accidental overwrite
    if [[ -f "$env_file" ]]; then
        cp "$env_file" "${env_file}.bak.$(date +%s)"
        warn "Existing .env backed up"
    fi

    cp "${SCRIPT_DIR}/.env.example" "$env_file"
    chmod 600 "$env_file"

    # Sanitise user input: strip characters that could break sed or shell quoting
    _sanitise() { printf '%s' "$1" | tr -d '|"\\`$\n'; }

    sed -i "s|CUSTOMER_NAME=\"CHANGEME\"|CUSTOMER_NAME=\"$(_sanitise "$i_customer")\"|" "$env_file"
    sed -i "s|DEVICE_USER=\"CHANGEME\"|DEVICE_USER=\"$(_sanitise "$i_user")\"|" "$env_file"
    sed -i "s|DEVICE_HOSTNAME=\"dev\"|DEVICE_HOSTNAME=\"$(_sanitise "$i_hostname")\"|" "$env_file"
    sed -i "s|SWAP_SIZE=\"32G\"|SWAP_SIZE=\"$(_sanitise "$i_swap")\"|" "$env_file"
    sed -i "s|INSTALL_TAILSCALE=\"false\"|INSTALL_TAILSCALE=\"$(_sanitise "$i_tailscale")\"|" "$env_file"
    sed -i "s|GIT_USER_NAME=\"\"|GIT_USER_NAME=\"$(_sanitise "$i_git_name")\"|" "$env_file"
    sed -i "s|GIT_USER_EMAIL=\"\"|GIT_USER_EMAIL=\"$(_sanitise "$i_git_email")\"|" "$env_file"
    sed -i "s|INSTALL_CLAUDE=\"true\"|INSTALL_CLAUDE=\"$(_sanitise "$i_claude")\"|" "$env_file"
    sed -i "s|INSTALL_ARASUL_TUI=\"true\"|INSTALL_ARASUL_TUI=\"$(_sanitise "$i_tui")\"|" "$env_file"

    log ".env file created: ${env_file}"
    echo ""
}

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
check_platform() {
    PLATFORM="${PLATFORM:-$(detect_platform)}"
    DEVICE_MODEL=$(detect_model)

    case "$PLATFORM" in
        jetson)
            if [[ -f /etc/nv_tegra_release ]]; then
                local l4t_version
                l4t_version=$(head -1 /etc/nv_tegra_release | sed 's/.*R\([0-9]*\).*/\1/')
                log "Jetson detected: ${DEVICE_MODEL} (L4T R${l4t_version})"
            else
                log "Jetson detected: ${DEVICE_MODEL}"
            fi
            ;;
        raspberry_pi)
            log "Raspberry Pi detected: ${DEVICE_MODEL}"
            ;;
        generic)
            log "Generic Linux detected: ${DEVICE_MODEL}"
            ;;
    esac
}

check_user_exists() {
    if ! id "$REAL_USER" &>/dev/null; then
        err "User '${REAL_USER}' does not exist on this system"
        err "Please fix DEVICE_USER in .env"
        exit 1
    fi
}

# ---------------------------------------------------------------------------
# Pre-flight checks: SSH keys, internet, disk space
# ---------------------------------------------------------------------------
pre_flight_checks() {
    local warnings=0

    echo "╭─────────────────────────────────────╮"
    echo "│  Pre-Flight Checks                  │"
    echo "╰─────────────────────────────────────╯"
    echo ""

    # Check 1: SSH authorized_keys
    local auth_keys="${REAL_HOME}/.ssh/authorized_keys"
    if [[ ! -f "$auth_keys" ]] || [[ ! -s "$auth_keys" ]]; then
        warn "No SSH key found for ${REAL_USER}!"
        echo ""
        echo "  SSH keys are required for secure remote access."
        echo "  After setup, password login will be disabled."
        echo ""
        echo "  On your Mac, run these commands:"
        echo ""
        echo "    # Generate SSH key (if you don't have one):"
        echo "    ssh-keygen -t ed25519"
        echo ""
        echo "    # Copy your key to this device:"
        echo "    ssh-copy-id ${REAL_USER}@$(hostname).local"
        echo ""
        echo "  Then run setup.sh again."
        echo ""
        read -rp "  Continue without SSH key? (SSH hardening will be skipped) [y/N]: " skip_ssh
        if [[ "${skip_ssh,,}" != "y" && "${skip_ssh,,}" != "yes" ]]; then
            info "Setup cancelled. Copy your SSH key first, then try again."
            exit 0
        fi
        SKIP_SSH_HARDENING=true
        warnings=$((warnings + 1))
    else
        local key_count
        key_count=$(wc -l < "$auth_keys")
        log "SSH keys: ${key_count} key(s) found"
    fi

    # Check 2: Internet connectivity
    if ! check_internet; then
        echo "  Some steps require internet (Docker images, npm packages)."
        read -rp "  Continue anyway? [y/N]: " continue_offline
        if [[ "${continue_offline,,}" != "y" ]]; then
            exit 0
        fi
        warnings=$((warnings + 1))
    else
        log "Internet: OK"
    fi

    # Check 3: Sufficient disk space (min 5GB)
    local free_mb
    free_mb=$(df -m / | awk 'NR==2 {print $4}')
    if (( free_mb < 5000 )); then
        warn "Low disk space: ${free_mb}MB free (5GB recommended)"
        warnings=$((warnings + 1))
    else
        log "Disk space: ${free_mb}MB free"
    fi

    echo ""
    if (( warnings > 0 )); then
        warn "${warnings} warning(s). Setup may not complete fully."
    else
        log "All pre-flight checks passed!"
    fi
    echo ""
}

setup_logging() {
    mkdir -p "$LOG_DIR"
    local logfile
    logfile="${LOG_DIR}/setup-$(date +%Y%m%d-%H%M%S).log"
    exec > >(tee -a "$logfile")
    exec 2>&1
    log "Logfile: ${logfile}"
}

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
INTERACTIVE=false
parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --skip-reboot)   SKIP_REBOOT=true; shift ;;
            --step)          if [[ $# -lt 2 ]]; then err "--step requires a step number"; exit 1; fi
                             SINGLE_STEP="$2"; shift 2 ;;
            --interactive)   INTERACTIVE=true; shift ;;
            --auto)          AUTO=true; shift ;;
            -h|--help)
                echo "Usage: sudo ./setup.sh [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  --interactive    Interactive mode (generates .env + step selection)"
                echo "  --auto           Run all applicable steps without wizard"
                echo "  --skip-reboot    No reboot after setup"
                echo "  --step N         Run only step N (1-9)"
                echo "  -h, --help       Show this help"
                echo ""
                echo "Default behavior shows a step selection wizard."
                echo "Use --auto for unattended / scripted installs."
                echo ""
                echo "Steps:"
                echo "  1  System optimization (disable desktop, tune kernel)"
                echo "  2  Network (hostname, mDNS, firewall)"
                echo "  3  SSH hardening (key-only auth, fail2ban)"
                echo "  4  Storage setup (NVMe/SSD, swap)"
                echo "  5  Docker + Compose"
                echo "  6  Dev tools (Node.js, Python, Claude Code)"
                echo "  7  Quality of life (tmux, aliases, prompt)"
                echo "  8  Headless browser (Playwright + Chromium)"
                echo "  9  n8n workflow automation (Docker stack)"
                exit 0
                ;;
            *) err "Unknown option: $1"; exit 1 ;;
        esac
    done
}

# ---------------------------------------------------------------------------
# Run a setup script
# ---------------------------------------------------------------------------
run_script() {
    local num="$1"
    local name="$2"
    local script="${SCRIPT_DIR}/scripts/${num}-${name}.sh"

    if [[ ! -f "$script" ]]; then
        err "Script not found: $script"
        return 1
    fi

    step "Step ${num}: ${name}"

    # Export config variables for subscripts
    export REAL_USER REAL_HOME SWAP_SIZE PLATFORM DEVICE_MODEL
    export STORAGE_DEVICE STORAGE_MOUNT STORAGE_TYPE
    export DEVICE_USER DEVICE_HOSTNAME CUSTOMER_NAME
    export INSTALL_TAILSCALE INSTALL_CLAUDE INSTALL_OLLAMA
    export INSTALL_ARASUL_TUI INSTALL_N8N
    export NODE_VERSION POWER_MODE
    export GIT_USER_NAME GIT_USER_EMAIL
    export DOCKER_LOG_MAX_SIZE DOCKER_LOG_MAX_FILES
    export STATIC_IP STATIC_GATEWAY
    export SKIP_SSH_HARDENING
    export SCRIPT_DIR

    local rc=0
    bash "$script" || rc=$?

    if [[ $rc -eq 0 ]]; then
        log "Step ${num} completed successfully"
    elif [[ $rc -eq 2 ]]; then
        warn "Step ${num} skipped (already configured)"
    else
        err "Step ${num} failed (exit code: ${rc})"
        err "Check logs: ${LOG_DIR}/"
        exit 1
    fi
}

# ---------------------------------------------------------------------------
# Step selection wizard
# ---------------------------------------------------------------------------

# Step descriptions (index 0-8 for steps 1-9)
STEP_NAMES=(
    "System optimization (disable desktop, tune kernel)"
    "Network (hostname, mDNS, firewall)"
    "SSH hardening (key-only auth, fail2ban)"
    "Storage setup (NVMe/SSD, swap)"
    "Docker + Compose"
    "Dev tools (Node.js, Python, Git, Claude Code)"
    "Quality of life (tmux, aliases, prompt)"
    "Headless browser (Playwright + Chromium)"
    "n8n workflow automation"
)

# Selected steps (1=selected, 0=not) — index 0-8 for steps 1-9
declare -a SELECTED_STEPS

# Compute platform-aware default selections
compute_step_defaults() {
    SELECTED_STEPS=(1 1 1 1 1 1 1 1 0)

    # Storage: off if no external storage detected
    if [[ -z "$STORAGE_DEVICE" ]]; then
        SELECTED_STEPS[3]=0
    fi

    # Browser: off on RPi with <=4GB RAM
    if [[ "$PLATFORM" == "raspberry_pi" ]]; then
        local ram_mb
        ram_mb=$(detect_ram_mb 2>/dev/null || echo 0)
        if (( ram_mb > 0 && ram_mb <= 4096 )); then
            SELECTED_STEPS[7]=0
        fi
    fi

    # Generic: storage off if no external drive
    if [[ "$PLATFORM" == "generic" ]] && [[ -z "$STORAGE_DEVICE" ]]; then
        SELECTED_STEPS[3]=0
    fi

    # n8n: follow .env config
    if [[ "${INSTALL_N8N}" == "true" ]]; then
        SELECTED_STEPS[8]=1
    fi
}

# Load previous selections from state file
load_setup_state() {
    local state_file="${REAL_HOME}/.arasul/setup-state.json"
    [[ -f "$state_file" ]] || return 0
    command -v python3 &>/dev/null || return 0

    local saved
    saved=$(python3 << PYEOF
import json
try:
    with open("${state_file}") as f:
        data = json.load(f)
    steps = data.get("steps", {})
    for i in range(1, 10):
        v = steps.get(str(i))
        if v is not None:
            print(f"{i - 1}={'1' if v else '0'}")
except Exception:
    pass
PYEOF
    ) || return 0

    while IFS='=' read -r idx val; do
        if [[ -n "$idx" ]] && [[ -n "$val" ]]; then
            SELECTED_STEPS[idx]=$val
        fi
    done <<< "$saved"

    log "Loaded previous selections from ${state_file}"
}

# Save current selections to state file
save_setup_state() {
    command -v python3 &>/dev/null || return 0

    local state_dir="${REAL_HOME}/.arasul"
    mkdir -p "$state_dir"
    chown "$REAL_USER:$REAL_USER" "$state_dir" 2>/dev/null || true

    local state_file="${state_dir}/setup-state.json"

    python3 << PYEOF
import json
from datetime import datetime
data = {
    "version": 1,
    "timestamp": datetime.now().isoformat(),
    "platform": "${PLATFORM}",
    "steps": {
        "1": $([ "${SELECTED_STEPS[0]}" = "1" ] && echo "True" || echo "False"),
        "2": $([ "${SELECTED_STEPS[1]}" = "1" ] && echo "True" || echo "False"),
        "3": $([ "${SELECTED_STEPS[2]}" = "1" ] && echo "True" || echo "False"),
        "4": $([ "${SELECTED_STEPS[3]}" = "1" ] && echo "True" || echo "False"),
        "5": $([ "${SELECTED_STEPS[4]}" = "1" ] && echo "True" || echo "False"),
        "6": $([ "${SELECTED_STEPS[5]}" = "1" ] && echo "True" || echo "False"),
        "7": $([ "${SELECTED_STEPS[6]}" = "1" ] && echo "True" || echo "False"),
        "8": $([ "${SELECTED_STEPS[7]}" = "1" ] && echo "True" || echo "False"),
        "9": $([ "${SELECTED_STEPS[8]}" = "1" ] && echo "True" || echo "False")
    }
}
with open("${state_file}", "w") as f:
    json.dump(data, f, indent=2)
PYEOF

    chown "$REAL_USER:$REAL_USER" "$state_file" 2>/dev/null || true
}

# Step selection via whiptail or dialog
select_steps_tui() {
    local tool="$1"
    local args=()

    for i in $(seq 0 8); do
        local tag=$((i + 1))
        local status
        [[ "${SELECTED_STEPS[$i]}" == "1" ]] && status="ON" || status="OFF"
        args+=("$tag" "${STEP_NAMES[$i]}" "$status")
    done

    local choices
    choices=$("$tool" --title "  Arasul — Step Selection  " \
        --checklist "Select setup steps (Space to toggle, Enter to confirm):" \
        20 72 9 \
        "${args[@]}" \
        3>&1 1>&2 2>&3)

    local rc=$?
    if [[ $rc -ne 0 ]]; then
        warn "Setup cancelled."
        exit 0
    fi

    # Reset all to 0, then enable selected
    SELECTED_STEPS=(0 0 0 0 0 0 0 0 0)
    # shellcheck disable=SC2086
    for s in $choices; do
        local num="${s//\"/}"
        SELECTED_STEPS[num - 1]=1
    done
}

# Text-based fallback when whiptail/dialog unavailable
select_steps_text() {
    echo ""
    echo -e "${CYAN}  Select setup steps:${NC}"
    echo ""

    while true; do
        for i in $(seq 0 8); do
            local tag=$((i + 1))
            local mark
            [[ "${SELECTED_STEPS[$i]}" == "1" ]] && mark="x" || mark=" "
            printf "  [%s] %d. %s\n" "$mark" "$tag" "${STEP_NAMES[$i]}"
        done
        echo ""
        read -rp "  Toggle (1-9), 'a' all, 'n' none, Enter to start: " choice

        case "$choice" in
            [1-9])
                local idx=$((choice - 1))
                [[ "${SELECTED_STEPS[idx]}" == "1" ]] && SELECTED_STEPS[idx]=0 || SELECTED_STEPS[idx]=1
                # Move cursor up to redraw (9 lines + 1 blank + 1 prompt = 11)
                printf '\033[11A\033[0J'
                ;;
            a|A)
                SELECTED_STEPS=(1 1 1 1 1 1 1 1 1)
                printf '\033[11A\033[0J'
                ;;
            n|N)
                SELECTED_STEPS=(0 0 0 0 0 0 0 0 0)
                printf '\033[11A\033[0J'
                ;;
            "")
                break
                ;;
            *)
                # Invalid input — clear prompt line only
                printf '\033[1A\033[0K'
                ;;
        esac
    done
}

# Detailed step selection (power-user fallback)
select_steps_detailed() {
    if command -v whiptail &>/dev/null; then
        select_steps_tui "whiptail"
    elif command -v dialog &>/dev/null; then
        select_steps_tui "dialog"
    else
        select_steps_text
    fi
}

# Smart step selection: show auto-detected plan, confirm with Y/n
smart_step_selection() {
    echo "╭─────────────────────────────────────╮"
    echo "│  Installation Plan                  │"
    echo "╰─────────────────────────────────────╯"
    echo ""

    compute_step_defaults
    load_setup_state

    # SSH: disable if no key found in pre-flight
    if [[ "${SKIP_SSH_HARDENING}" == "true" ]]; then
        SELECTED_STEPS[2]=0
    fi

    echo "  The following will be configured:"
    echo ""
    for i in $(seq 0 8); do
        local num=$((i + 1))
        if [[ "${SELECTED_STEPS[$i]}" == "1" ]]; then
            printf "  ✓ Step %d: %s\n" "$num" "${STEP_NAMES[$i]}"
        else
            printf "  ○ Step %d: %s\n" "$num" "${STEP_NAMES[$i]}"
        fi
    done

    echo ""
    read -rp "  Proceed? [Y/n/customize]: " choice

    case "${choice,,}" in
        n|no)
            info "Setup cancelled."
            exit 0
            ;;
        c|customize)
            select_steps_detailed
            ;;
        *)
            # Proceed with smart defaults
            ;;
    esac

    save_setup_state
}

# Run a step with storage-type awareness
run_step() {
    local step="$1"

    case "$step" in
        1) run_script "01" "system-optimize" ;;
        2) run_script "02" "network-setup" ;;
        3) run_script "03" "ssh-harden" ;;
        4) run_script "04" "storage-setup" ;;
        5) run_script "05" "docker-setup" ;;
        6) run_script "06" "devtools-setup" ;;
        7) run_script "07" "quality-of-life" ;;
        8) run_script "08" "browser-setup" ;;
        9) run_script "09" "n8n-setup" ;;
    esac
}

# Run only the steps selected in SELECTED_STEPS[]
run_selected_steps() {
    for i in $(seq 0 8); do
        [[ "${SELECTED_STEPS[$i]}" == "0" ]] && continue
        run_step $((i + 1))
    done
}

# Run all applicable steps (--auto mode, old default behavior)
run_all_steps() {
    run_step 1
    run_step 2
    run_step 3
    run_step 4
    run_step 5
    run_step 6
    run_step 7
    run_step 8

    if [[ "${INSTALL_N8N}" == "true" ]]; then
        run_step 9
    else
        log "n8n skipped (INSTALL_N8N=false)"
    fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
parse_args "$@"
check_root

if [[ "$INTERACTIVE" == true ]]; then
    interactive_config
fi

load_config
check_platform
check_user_exists
pre_flight_checks
setup_logging

echo ""
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║  Arasul — Headless Dev Server Setup                          ║"
echo "╠═══════════════════════════════════════════════════════════════╣"
echo "║  Platform: ${PLATFORM} (${DEVICE_MODEL})"
echo "║  Customer: ${CUSTOMER_NAME}"
echo "║  User:     ${REAL_USER}"
echo "║  Home:     ${REAL_HOME}"
echo "║  Hostname: ${DEVICE_HOSTNAME}"
if [[ -n "$STORAGE_DEVICE" ]]; then
echo "║  Storage:  ${STORAGE_DEVICE} → ${STORAGE_MOUNT}"
else
echo "║  Storage:  ${STORAGE_MOUNT} (no external device)"
fi
echo "║  Swap:     ${SWAP_SIZE}"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""

if [[ -n "$SINGLE_STEP" ]]; then
    case "$SINGLE_STEP" in
        [1-9]) run_step "$SINGLE_STEP" ;;
        *) err "Invalid step: $SINGLE_STEP (must be 1-9)"; exit 1 ;;
    esac
elif [[ "$AUTO" == true ]]; then
    run_all_steps
else
    # Smart wizard: show plan, confirm, then run
    if [[ -t 0 ]]; then
        smart_step_selection
        run_selected_steps
    else
        # Non-interactive terminal (piped) — fall back to auto
        warn "Non-interactive terminal detected — running all steps"
        run_all_steps
    fi
fi

echo ""
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║  Setup complete!                                             ║"
echo "╠═══════════════════════════════════════════════════════════════╣"
echo "║  Next steps:                                                 ║"
echo "║  1. Set up SSH config (see config/mac-ssh-config)            ║"
echo "║  2. Reboot: sudo reboot                                     ║"
echo "║  3. Connect: ssh ${DEVICE_HOSTNAME}"
echo "║  4. Work: t → claude                                        ║"
echo "╚═══════════════════════════════════════════════════════════════╝"

if [[ "$SKIP_REBOOT" == false ]]; then
    echo ""
    warn "Reboot recommended: sudo reboot"
fi
