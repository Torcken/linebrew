#!/usr/bin/env bash
# Linebrew uninstaller
# Removes the Linebrew package, desktop entry, icons, and optionally config
# Usage: bash uninstall.sh

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
# Remove pip package
# ---------------------------------------------------------------------------

remove_package() {
    SYS_PYTHON=$(command -v /usr/bin/python3 2>/dev/null || command -v python3 2>/dev/null || true)

    if [ -z "$SYS_PYTHON" ]; then
        warn "python3 not found — skipping pip uninstall."
        return
    fi

    if "$SYS_PYTHON" -m pip show linebrew &>/dev/null 2>&1; then
        info "Removing Linebrew pip package…"
        "$SYS_PYTHON" -m pip uninstall -y linebrew 2>/dev/null \
            || "$SYS_PYTHON" -m pip uninstall -y --break-system-packages linebrew 2>/dev/null \
            || warn "pip uninstall failed — you may need to remove it manually."
        success "Pip package removed."
    else
        warn "Linebrew pip package not found — skipping."
    fi
}

# ---------------------------------------------------------------------------
# Remove desktop entry
# ---------------------------------------------------------------------------

remove_desktop_entry() {
    DESKTOP_FILE="$HOME/.local/share/applications/io.github.linebrew.Linebrew.desktop"

    if [ -f "$DESKTOP_FILE" ]; then
        info "Removing desktop entry…"
        rm -f "$DESKTOP_FILE"
        if command -v update-desktop-database &>/dev/null; then
            update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
        fi
        success "Desktop entry removed."
    else
        warn "Desktop entry not found — skipping."
    fi
}

# ---------------------------------------------------------------------------
# Remove icons
# ---------------------------------------------------------------------------

remove_icons() {
    ICON_NAME="io.github.linebrew.Linebrew.png"
    ICON_BASE="$HOME/.local/share/icons/hicolor"
    removed=0

    info "Removing icons…"
    for size in 16 22 24 32 48 64 96 128 256 512 1024; do
        ICON_FILE="$ICON_BASE/${size}x${size}/apps/$ICON_NAME"
        if [ -f "$ICON_FILE" ]; then
            rm -f "$ICON_FILE"
            removed=$((removed + 1))
        fi
    done

    if [ "$removed" -gt 0 ]; then
        if command -v gtk-update-icon-cache &>/dev/null; then
            gtk-update-icon-cache -qtf "$ICON_BASE" 2>/dev/null || true
        fi
        success "Icons removed ($removed sizes)."
    else
        warn "No icons found — skipping."
    fi
}

# ---------------------------------------------------------------------------
# Remove leftover entry-point binary
# ---------------------------------------------------------------------------

remove_binary() {
    BINARY="$HOME/.local/bin/linebrew"

    if [ -f "$BINARY" ]; then
        info "Removing binary $BINARY…"
        rm -f "$BINARY"
        success "Binary removed."
    fi
}

# ---------------------------------------------------------------------------
# Optionally remove config / user data
# ---------------------------------------------------------------------------

remove_config() {
    CONFIG_DIR="$HOME/.config/linebrew"

    if [ -d "$CONFIG_DIR" ]; then
        read -rp "Remove user configuration at $CONFIG_DIR? [y/N] " answer
        if [[ "${answer,,}" == "y" ]]; then
            rm -rf "$CONFIG_DIR"
            success "Configuration removed."
        else
            info "Keeping configuration at $CONFIG_DIR."
        fi
    fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
    echo ""
    echo -e "${BOLD}╔═══════════════════════════════════╗${RESET}"
    echo -e "${BOLD}║      Linebrew Uninstaller        ║${RESET}"
    echo -e "${BOLD}╚═══════════════════════════════════╝${RESET}"
    echo ""

    read -rp "This will remove Linebrew from your system. Continue? [y/N] " confirm
    if [[ "${confirm,,}" != "y" ]]; then
        info "Aborted."
        exit 0
    fi
    echo ""

    remove_package
    remove_desktop_entry
    remove_icons
    remove_binary
    remove_config

    echo ""
    success "Linebrew has been uninstalled."
    echo ""
}

main "$@"
