#!/bin/bash

# System Detection Script for Modular Dotfiles
# Detects platform, desktop environment, and available features

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m'

# Detection functions

detect_platform() {
    if [ -f /etc/arch-release ]; then
        echo "arch"
    elif [ -f /etc/ubuntu-release ] || [ -f /etc/debian_version ]; then
        echo "ubuntu"
    elif [ -f /etc/fedora-release ]; then
        echo "fedora"
    elif [ -f /etc/centos-release ]; then
        echo "centos"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        echo "linux"
    else
        echo "unknown"
    fi
}

detect_desktop() {
    if [ -n "${WAYLAND_DISPLAY:-}" ] || [ "${XDG_SESSION_TYPE:-}" = "wayland" ]; then
        if [ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] || pgrep -x "Hyprland" >/dev/null 2>&1; then
            echo "wayland/hyprland"
        elif [ "${XDG_CURRENT_DESKTOP:-}" = "sway" ] || pgrep -x "sway" >/dev/null 2>&1; then
            echo "wayland/sway"
        else
            echo "wayland/generic"
        fi
    elif [ -n "${DISPLAY:-}" ]; then
        if [ "${XDG_CURRENT_DESKTOP:-}" = "i3" ] || pgrep -x "i3" >/dev/null 2>&1; then
            echo "x11/i3"
        elif [ "${XDG_CURRENT_DESKTOP:-}" = "GNOME" ]; then
            echo "x11/gnome"
        elif [ "${XDG_CURRENT_DESKTOP:-}" = "KDE" ]; then
            echo "x11/kde"
        else
            echo "x11/generic"
        fi
    else
        echo "terminal"
    fi
}

detect_package_manager() {
    if command -v pacman >/dev/null 2>&1; then
        echo "pacman"
    elif command -v apt >/dev/null 2>&1; then
        echo "apt"
    elif command -v dnf >/dev/null 2>&1; then
        echo "dnf"
    elif command -v yum >/dev/null 2>&1; then
        echo "yum"
    elif command -v brew >/dev/null 2>&1; then
        echo "brew"
    elif command -v nix >/dev/null 2>&1; then
        echo "nix"
    else
        echo "unknown"
    fi
}

detect_shell() {
    if [ -n "${ZSH_VERSION:-}" ]; then
        echo "zsh"
    elif [ -n "${BASH_VERSION:-}" ]; then
        echo "bash"
    elif [ -n "${version:-}" ]; then
        echo "fish"
    else
        echo "unknown"
    fi
}

detect_terminal() {
    if [ -n "${ALACRITTY_SOCKET:-}" ] || [ "${TERM_PROGRAM:-}" = "Alacritty" ]; then
        echo "alacritty"
    elif [ "${TERM_PROGRAM:-}" = "iTerm.app" ]; then
        echo "iterm2"
    elif [ "${TERM_PROGRAM:-}" = "Terminal.app" ]; then
        echo "terminal-app"
    elif [ -n "${KITTY_WINDOW_ID:-}" ]; then
        echo "kitty"
    elif [ "${TERM:-}" = "foot" ]; then
        echo "foot"
    elif [ "${TERM:-}" = "wezterm" ]; then
        echo "wezterm"
    else
        echo "unknown"
    fi
}

detect_available_modules() {
    local modules=()
    
    # Bluetooth
    if command -v bluetoothctl >/dev/null 2>&1; then
        modules+=("bluetooth")
    fi
    
    # Power management
    if [ -d /sys/class/power_supply ] && ls /sys/class/power_supply/BAT* >/dev/null 2>&1; then
        modules+=("power-management")
    fi
    
    # Networking
    if command -v networkmanager >/dev/null 2>&1 || command -v nmcli >/dev/null 2>&1; then
        modules+=("networking")
    fi
    
    # Docker
    if command -v docker >/dev/null 2>&1; then
        modules+=("containers")
    fi
    
    # Development languages
    command -v python >/dev/null 2>&1 && modules+=("python")
    command -v node >/dev/null 2>&1 && modules+=("javascript")
    command -v rustc >/dev/null 2>&1 && modules+=("rust")
    command -v go >/dev/null 2>&1 && modules+=("go")
    
    # Media
    command -v mpv >/dev/null 2>&1 && modules+=("media")
    
    # Security
    command -v gpg >/dev/null 2>&1 && modules+=("security")
    
    printf '%s\n' "${modules[@]}"
}

get_system_info() {
    echo "🖥️  System Information:"
    echo "Platform: $(detect_platform)"
    echo "Desktop: $(detect_desktop)"
    echo "Package Manager: $(detect_package_manager)"
    echo "Shell: $(detect_shell)"
    echo "Terminal: $(detect_terminal)"
    echo ""
    echo "📦 Available Modules:"
    detect_available_modules | sed 's/^/  - /'
}

# Export detection functions for use in other scripts
export -f detect_platform detect_desktop detect_package_manager detect_shell detect_terminal detect_available_modules

# If script is run directly, show system info
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    case "${1:-info}" in
        "platform")
            detect_platform
            ;;
        "desktop")
            detect_desktop
            ;;
        "package-manager")
            detect_package_manager
            ;;
        "shell")
            detect_shell
            ;;
        "terminal")
            detect_terminal
            ;;
        "modules")
            detect_available_modules
            ;;
        "info"|*)
            get_system_info
            ;;
    esac
fi