#!/usr/bin/env bash
# Linebrew installer
# Supports: Ubuntu/Debian, Fedora/RHEL, Arch Linux, openSUSE
# Usage: bash install.sh

set -euo pipefail

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
RESET='\033[0m'

info()    { echo -e "${BOLD}[Linebrew]${RESET} $*"; }
success() { echo -e "${GREEN}[Linebrew] ✓ $*${RESET}"; }
warn()    { echo -e "${YELLOW}[Linebrew] ⚠ $*${RESET}"; }
error()   { echo -e "${RED}[Linebrew] ✗ $*${RESET}" >&2; }

# ---------------------------------------------------------------------------
# Detect Linux distribution
# ---------------------------------------------------------------------------

detect_distro() {
    if [ -f /etc/os-release ]; then
        # shellcheck disable=SC1091
        source /etc/os-release
        DISTRO="${ID:-unknown}"
        DISTRO_LIKE="${ID_LIKE:-}"
    else
        DISTRO="unknown"
        DISTRO_LIKE=""
    fi
}

# ---------------------------------------------------------------------------
# Install system dependencies
# ---------------------------------------------------------------------------

install_deps_debian() {
    info "Installing dependencies for Ubuntu/Debian…"
    sudo apt-get update -qq
    sudo apt-get install -y \
        python3 \
        python3-pip \
        python3-gi \
        python3-gi-cairo \
        gir1.2-gtk-4.0 \
        gir1.2-adw-1 \
        libadwaita-1-0 \
        libgtk-4-1
    success "Dependencies installed."
}

install_deps_fedora() {
    info "Installing dependencies for Fedora/RHEL…"
    sudo dnf install -y \
        python3 \
        python3-pip \
        python3-gobject \
        gtk4 \
        libadwaita
    success "Dependencies installed."
}

install_deps_arch() {
    info "Installing dependencies for Arch Linux…"
    sudo pacman -Sy --noconfirm \
        python \
        python-pip \
        python-gobject \
        gtk4 \
        libadwaita
    success "Dependencies installed."
}

install_deps_opensuse() {
    info "Installing dependencies for openSUSE…"
    sudo zypper install -y \
        python3 \
        python3-pip \
        python3-gobject \
        typelib-1_0-Gtk-4_0 \
        typelib-1_0-Adw-1 \
        libadwaita-1-0
    success "Dependencies installed."
}

install_system_deps() {
    detect_distro

    case "$DISTRO" in
        ubuntu|debian|linuxmint|pop|elementary|zorin)
            install_deps_debian ;;
        fedora|rhel|centos|rocky|alma)
            install_deps_fedora ;;
        arch|manjaro|endeavouros|garuda)
            install_deps_arch ;;
        opensuse*|sles)
            install_deps_opensuse ;;
        *)
            # Try ID_LIKE fallback
            if echo "$DISTRO_LIKE" | grep -qE "debian|ubuntu"; then
                install_deps_debian
            elif echo "$DISTRO_LIKE" | grep -q "fedora"; then
                install_deps_fedora
            elif echo "$DISTRO_LIKE" | grep -q "arch"; then
                install_deps_arch
            elif echo "$DISTRO_LIKE" | grep -q "suse"; then
                install_deps_opensuse
            else
                warn "Unknown distro '${DISTRO}'. Skipping automatic dependency install."
                warn "Please install: python3, python3-gi, gtk4, libadwaita manually."
            fi
            ;;
    esac
}

# ---------------------------------------------------------------------------
# Check for Homebrew
# ---------------------------------------------------------------------------

check_homebrew() {
    if command -v brew &>/dev/null; then
        BREW_VER=$(brew --version | head -1)
        success "Homebrew found: $BREW_VER"
        return 0
    fi

    # Check common Linux paths
    for p in /home/linuxbrew/.linuxbrew/bin/brew /opt/homebrew/bin/brew; do
        if [ -x "$p" ]; then
            success "Homebrew found at $p"
            warn "Add it to PATH: export PATH=\"$(dirname "$p"):\$PATH\""
            return 0
        fi
    done

    warn "Homebrew not found."
    read -rp "Install Homebrew now? [y/N] " answer
    if [[ "${answer,,}" == "y" ]]; then
        info "Installing Homebrew…"
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        # Add linuxbrew to current shell PATH
        if [ -x /home/linuxbrew/.linuxbrew/bin/brew ]; then
            eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"
            success "Homebrew installed."
        fi
    else
        warn "Skipping Homebrew installation. Linebrew requires Homebrew to function."
    fi
}

# ---------------------------------------------------------------------------
# Install Linebrew
# ---------------------------------------------------------------------------

install_linebrew() {
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

    info "Installing Linebrew via pip…"
    # Use system Python to avoid GLib conflicts with conda/pyenv environments
    SYS_PYTHON=$(command -v /usr/bin/python3 || command -v python3)
    "$SYS_PYTHON" -m pip install --user --no-deps --break-system-packages "$SCRIPT_DIR" 2>/dev/null \
        || "$SYS_PYTHON" -m pip install --user --no-deps "$SCRIPT_DIR"
    success "Linebrew installed."

    # Install .desktop file
    DESKTOP_SRC="$SCRIPT_DIR/data/io.github.linebrew.Linebrew.desktop"
    DESKTOP_DST="$HOME/.local/share/applications/io.github.linebrew.Linebrew.desktop"
    APPS_DIR="$(dirname "$DESKTOP_DST")"

    if [ -f "$DESKTOP_SRC" ]; then
        mkdir -p "$APPS_DIR"
        cp "$DESKTOP_SRC" "$DESKTOP_DST"
        # Update the desktop database so the app appears in launchers
        if command -v update-desktop-database &>/dev/null; then
            update-desktop-database "$APPS_DIR" 2>/dev/null || true
        fi
        success ".desktop file installed to $DESKTOP_DST"
    fi

    # Install icons at all available sizes
    ICON_NAME="io.github.linebrew.Linebrew.png"
    ICON_BASE="$HOME/.local/share/icons/hicolor"
    for size in 16 22 24 32 48 64 96 128 256 512 1024; do
        ICON_SRC="$SCRIPT_DIR/data/icons/hicolor/${size}x${size}/apps/$ICON_NAME"
        ICON_DST="$ICON_BASE/${size}x${size}/apps/$ICON_NAME"
        if [ -f "$ICON_SRC" ]; then
            mkdir -p "$(dirname "$ICON_DST")"
            cp "$ICON_SRC" "$ICON_DST"
        fi
    done
    if command -v gtk-update-icon-cache &>/dev/null; then
        gtk-update-icon-cache -qtf "$ICON_BASE" 2>/dev/null || true
    fi
    success "Icons installed (all sizes)."
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
    echo ""
    echo -e "${BOLD}╔═══════════════════════════════════╗${RESET}"
    echo -e "${BOLD}║       Linebrew Installer         ║${RESET}"
    echo -e "${BOLD}╚═══════════════════════════════════╝${RESET}"
    echo ""

    install_system_deps
    check_homebrew
    install_linebrew

    echo ""
    success "Installation complete!"
    echo ""
    info "Run Linebrew with:  ${BOLD}linebrew${RESET}"
    info "Or launch it from your application menu."
    echo ""

    # Check if ~/.local/bin is in PATH
    if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
        warn "~/.local/bin is not in your PATH."
        warn "Add this to your shell profile:"
        echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
    fi
}

main "$@"
