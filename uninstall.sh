#!/usr/bin/env sh
# ============================================================================
#  Wobble Uninstaller (standalone)
#  Removes the installed runtime, launcher, and shell completions.
#  Your projects are NEVER touched. Config/cache is kept unless --purge.
#
#  Usage:
#    sh uninstall.sh [--purge] [--yes] [--root DIR] [--bin DIR]
# ============================================================================
set -eu

if [ -z "${HOME:-}" ]; then
    printf 'error  HOME is not set; refusing to guess where Wobble lives.\n' >&2
    exit 1
fi

RESET="\033[0m"
BOLD="\033[1m"
DIM="\033[2m"
CYAN="\033[36m"
GREEN="\033[32m"
YELLOW="\033[33m"
RED="\033[31m"

if [ ! -t 1 ] || [ -n "${NO_COLOR:-}" ]; then
    RESET=""; BOLD=""; DIM=""; CYAN=""; GREEN=""; YELLOW=""; RED=""
fi

info() { printf '  %sinfo%s   %s\n' "$CYAN" "$RESET" "$1"; }
ok()   { printf '  %sok%s     %s\n' "$GREEN$BOLD" "$RESET" "$1"; }
warn() { printf '  %swarn%s   %s\n' "$YELLOW$BOLD" "$RESET" "$1"; }
fail() { printf '  %serror%s  %s\n' "$RED$BOLD" "$RESET" "$1" >&2; }

usage() {
    printf '%sUsage:%s sh uninstall.sh [--purge] [--yes] [--root DIR] [--bin DIR]\n\n' "$BOLD" "$RESET"
    printf '  --purge      Also remove ~/.wobble (registry, plugins, keystore) and ~/.config/wobble\n'
    printf '  --yes, -y    Do not ask for confirmation\n'
    printf '  --root DIR   App install directory (default: ~/.local/share/wobble)\n'
    printf '  --bin DIR    Launcher directory       (default: ~/.local/bin)\n'
    printf '  -h, --help   Show this help\n\n'
}

INSTALL_ROOT="${WOBBLE_INSTALL_DIR:-$HOME/.local/share/wobble}"
BIN_DIR="${WOBBLE_BIN_DIR:-$HOME/.local/bin}"
PURGE=0
ASSUME_YES=0

while [ $# -gt 0 ]; do
    case "$1" in
        --root|--prefix) INSTALL_ROOT="$2"; shift 2 ;;
        --bin)           BIN_DIR="$2"; shift 2 ;;
        --purge)         PURGE=1; shift ;;
        --yes|-y)        ASSUME_YES=1; shift ;;
        -h|--help)       usage; exit 0 ;;
        *) fail "Unknown option: $1"; usage; exit 2 ;;
    esac
done

case "$INSTALL_ROOT" in
    "/") fail "Refusing to uninstall from unsafe location: '/'"; exit 1 ;;
    /*) ;;
    *) fail "Install root must be an absolute path: '$INSTALL_ROOT'"; exit 1 ;;
esac
# Normalize trailing slashes without relying on readlink -f (not portable to toybox).
while [ "${INSTALL_ROOT%/}" != "$INSTALL_ROOT" ]; do
    INSTALL_ROOT="${INSTALL_ROOT%/}"
done
case "/$INSTALL_ROOT/" in
    *"/../"*|*"/./"*) fail "Refusing install root containing '.' or '..': '$INSTALL_ROOT'"; exit 1 ;;
esac
case "$INSTALL_ROOT" in
    ""|"/"|"$HOME") fail "Refusing to uninstall from unsafe location: '$INSTALL_ROOT'"; exit 1 ;;
esac
case "$BIN_DIR" in
    ""|"/") fail "Refusing to use unsafe launcher directory: '$BIN_DIR'"; exit 1 ;;
esac

printf '\n%sWobble uninstaller%s\n' "$BOLD" "$RESET"
printf '  %sapp dir%s   %s\n' "$DIM" "$RESET" "$INSTALL_ROOT"
printf '  %slauncher%s  %s\n' "$DIM" "$RESET" "$BIN_DIR/wob"
printf '  %spurge%s     %s\n\n' "$DIM" "$RESET" "$([ "$PURGE" = 1 ] && echo yes || echo no)"

if [ "$ASSUME_YES" != 1 ]; then
    if [ -t 0 ]; then
        printf '  Remove Wobble? Your project folders are preserved. [y/N] '
        read -r ANSWER || ANSWER=""
        case "$ANSWER" in
            y|Y|yes|YES) ;;
            *) info "Cancelled."; exit 0 ;;
        esac
    else
        fail "Refusing to uninstall without confirmation. Re-run with --yes."
        exit 1
    fi
fi

REMOVED=0
remove_launcher() {
    TARGET="$1"
    [ -e "$TARGET" ] || [ -L "$TARGET" ] || return 0
    if [ -L "$TARGET" ]; then
        LINK=$(readlink "$TARGET" 2>/dev/null || true)
        case "$LINK" in
            *wobble*bin/wob) rm -f "$TARGET" && ok "removed legacy symlink $TARGET" && REMOVED=1 ;;
            *) warn "kept foreign symlink $TARGET -> $LINK" ;;
        esac
    elif [ -f "$TARGET" ] && grep -q "Wobble launcher (auto-generated" "$TARGET" 2>/dev/null; then
        rm -f "$TARGET" && ok "removed launcher $TARGET" && REMOVED=1
    else
        warn "kept foreign executable $TARGET"
    fi
}

remove_launcher "$BIN_DIR/wob"
remove_launcher "$BIN_DIR/wob-rescue"
if [ -n "${PREFIX:-}" ] && [ "$PREFIX/bin/wob" != "$BIN_DIR/wob" ]; then
    remove_launcher "$PREFIX/bin/wob"
    remove_launcher "$PREFIX/bin/wob-rescue"
fi

# App runtime and manifest (never recursively delete the whole root: it may
# contain files the user put there). Only touch it when it is recognisably a
# Wobble installation, so a mistyped --root cannot delete unrelated files.
if [ -f "$INSTALL_ROOT/app/wob.py" ] || [ -f "$INSTALL_ROOT/install.json" ]; then
    for ITEM in "$INSTALL_ROOT/app" "$INSTALL_ROOT/.app.old" \
                "$INSTALL_ROOT/snapshot" "$INSTALL_ROOT/.snapshot.old" \
                "$INSTALL_ROOT/repair-backups" \
                "$INSTALL_ROOT/rescue.py" "$INSTALL_ROOT/rescue.sh" \
                "$INSTALL_ROOT/install.json"; do
        if [ -e "$ITEM" ]; then
            rm -rf "$ITEM" && ok "removed $ITEM" && REMOVED=1
        fi
    done
    for ITEM in "$INSTALL_ROOT"/.app.tmp-* "$INSTALL_ROOT"/.snapshot.tmp-*; do
        [ -e "$ITEM" ] || continue
        rm -rf "$ITEM" && REMOVED=1
    done
    rmdir "$INSTALL_ROOT" 2>/dev/null && ok "removed $INSTALL_ROOT" || true
else
    warn "No Wobble runtime found at $INSTALL_ROOT (nothing to delete there)"
fi

# Shell completions written by the installer.
for COMPLETION in \
    "$HOME/.local/share/bash-completion/completions/wob" \
    "$HOME/.local/share/zsh/site-functions/_wob"; do
    if [ -f "$COMPLETION" ] && grep -q "Wobble (wob)" "$COMPLETION" 2>/dev/null; then
        rm -f "$COMPLETION" && ok "removed completion $COMPLETION" && REMOVED=1
    fi
done

if [ "$PURGE" = 1 ]; then
    for DATA in "$HOME/.wobble" "$HOME/.config/wobble"; do
        if [ -d "$DATA" ]; then
            rm -rf "$DATA" && ok "purged $DATA" && REMOVED=1
        fi
    done
fi

if [ "$REMOVED" = 0 ]; then
    warn "Nothing to remove: Wobble does not appear to be installed at these paths."
fi

printf '\n  %sWobble has been uninstalled.%s Project directories and APKs were preserved.\n' "$BOLD" "$RESET"
if [ "$PURGE" != 1 ]; then
    printf '  %sConfig/cache kept in ~/.wobble and ~/.config/wobble (use --purge to remove).%s\n' "$DIM" "$RESET"
fi
printf '\n'
