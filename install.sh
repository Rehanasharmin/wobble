#!/usr/bin/env sh
# ============================================================================
#  Wobble Installer
#  Installs Wobble as standalone software: the runtime is copied into its own
#  application directory and a launcher is generated. Deleting the source
#  checkout afterwards does NOT break the `wob` command.
#
#  Usage:
#    sh install.sh                 # install from this checkout
#    curl -sL .../install.sh | sh  # install from GitHub (downloads a copy)
#    sh install.sh --root DIR --bin DIR --no-completion --no-path --force
# ============================================================================
set -eu

# --- ANSI fix: expand escapes at assignment time so the variables hold real
#     ESC bytes. Previously `CYAN="\033[36m"` stored the literal 6 characters
#     "\033[36m", and `printf '%s' "$CYAN"` printed them verbatim instead of
#     emitting a color code. `printf '\033…'` interprets the escape because it
#     is in the format string, so the variable gets the actual byte sequence.
RESET=$(printf '\033[0m')
BOLD=$(printf '\033[1m')
DIM=$(printf '\033[2m')
CYAN=$(printf '\033[36m')
GREEN=$(printf '\033[32m')
YELLOW=$(printf '\033[33m')
RED=$(printf '\033[31m')
MAGENTA=$(printf '\033[35m')

if [ ! -t 1 ] || [ -n "${NO_COLOR:-}" ]; then
    RESET=""; BOLD=""; DIM=""; CYAN=""; GREEN=""; YELLOW=""; RED=""; MAGENTA=""
fi

step() { printf '  %s[%s]%s %s\n' "$CYAN" "$1" "$RESET" "$2"; }
ok()   { printf '  %s[+]%s %s\n' "$GREEN$BOLD" "$RESET" "$1"; }
warn() { printf '  %s[!]%s %s\n' "$YELLOW$BOLD" "$RESET" "$1"; }
fail() { printf '  %s[x]%s %s\n' "$RED$BOLD" "$RESET" "$1" >&2; }

banner() {
    printf '\n%s' "$CYAN"
    cat <<'WOBBLE_ART'
  __        __   ____   ____   ____   _      _____
  \ \      / /  / __ \ |  _ \ | __ ) | |    | ____|
   \ \ /\ / /  | |  | || |_) ||  _ \ | |    |  _|
    \ V  V /   | |__| || |_) || |_) || |___ | |___|
     \_/\_/     \____/ |____/ |____/ |_____||_____|
WOBBLE_ART
    printf '%s' "$RESET"
    printf '  %sTermux -> Wobble -> Projects -> Frameworks -> Build -> Test -> APK/Web%s\n\n' "$DIM" "$RESET"
}

usage() {
    banner
    printf '%sUsage:%s sh install.sh [options]\n\n' "$BOLD" "$RESET"
    printf '  --root DIR        App install directory (default: ~/.local/share/wobble)\n'
    printf '  --bin DIR         Launcher directory       (default: ~/.local/bin)\n'
    printf '  --source DIR      Install from a local Wobble checkout\n'
    printf '  --force           Replace an existing foreign "wob" executable\n'
    printf '  --no-completion   Skip bash/zsh completion files\n'
    printf '  --no-path         Do not edit ~/.bashrc / ~/.zshrc / ~/.profile\n'
    printf '  --no-snapshot     Skip the offline recovery snapshot (~600 KB)\n'
    printf '  -h, --help        Show this help\n\n'
}

INSTALL_ROOT="${WOBBLE_INSTALL_DIR:-$HOME/.local/share/wobble}"
BIN_DIR="${WOBBLE_BIN_DIR:-$HOME/.local/bin}"
SOURCE_OVERRIDE=""
FORCE=0
COMPLETIONS=1
UPDATE_PATH=1
SNAPSHOT=1

while [ $# -gt 0 ]; do
    case "$1" in
        --root|--prefix) INSTALL_ROOT="$2"; shift 2 ;;
        --bin)           BIN_DIR="$2"; shift 2 ;;
        --source)        SOURCE_OVERRIDE="$2"; shift 2 ;;
        --force)         FORCE=1; shift ;;
        --no-completion) COMPLETIONS=0; shift ;;
        --no-path)       UPDATE_PATH=0; shift ;;
        --no-snapshot)   SNAPSHOT=0; shift ;;
        -h|--help)       usage; exit 0 ;;
        *) fail "Unknown option: $1"; usage; exit 2 ;;
    esac
done

banner

# ---------------------------------------------------------------------------
# 1. Locate a source tree
# ---------------------------------------------------------------------------
SOURCE=""
if [ -n "$SOURCE_OVERRIDE" ]; then
    SOURCE="$SOURCE_OVERRIDE"
    step "1/5" "Using source directory: $SOURCE"
else
    SELF="${0:-}"
    # When piped from curl, $0 is the shell itself ("sh", "bash", ...). In that
    # case there is no local checkout and the script downloads one. A plain
    # "install.sh" (as in `cd wobble && sh install.sh`) is a real file and must
    # be used, otherwise the installer would needlessly fetch from GitHub.
    case "$SELF" in
        ""|-sh|-bash|sh|bash|dash|ash|zsh|ksh) SELF="" ;;
    esac
    if [ -n "$SELF" ] && [ -f "$SELF" ]; then
        case "$SELF" in
            */*) SCRIPT_DIR="${SELF%/*}" ;;
            *) SCRIPT_DIR="." ;;
        esac
        SCRIPT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR" 2>/dev/null && pwd) || SCRIPT_DIR=""
        if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/wobble/cli.py" ]; then
            SOURCE="$SCRIPT_DIR"
            step "1/5" "Using local checkout: $SOURCE"
        fi
    fi
fi

TMP_DIR=""
cleanup() {
    if [ -n "$TMP_DIR" ] && [ -d "$TMP_DIR" ]; then
        rm -rf "$TMP_DIR"
    fi
}
trap cleanup EXIT INT TERM

if [ -z "$SOURCE" ]; then
    step "1/5" "No local checkout found; downloading Wobble..."
    TMP_DIR=$(mktemp -d 2>/dev/null || mktemp -d -t wobble)
    REPO_URL="https://github.com/Rehanasharmin/wobble.git"
    TARBALL_URL="https://codeload.github.com/Rehanasharmin/wobble/tar.gz/refs/heads/main"
    if command -v git >/dev/null 2>&1; then
        git clone --depth 1 "$REPO_URL" "$TMP_DIR/src" >/dev/null 2>&1 || {
            fail "git clone failed. Check your network connection."
            exit 1
        }
        SOURCE="$TMP_DIR/src"
    else
        if ! command -v curl >/dev/null 2>&1; then
            fail "Neither git nor curl is available. Install one first: pkg install -y git curl"
            exit 1
        fi
        curl -fsSL "$TARBALL_URL" -o "$TMP_DIR/wobble.tar.gz" || {
            fail "Download failed. Check your network connection."
            exit 1
        }
        mkdir -p "$TMP_DIR/src"
        tar -xzf "$TMP_DIR/wobble.tar.gz" -C "$TMP_DIR/src" --strip-components=1 || {
            fail "Could not extract the downloaded archive."
            exit 1
        }
        SOURCE="$TMP_DIR/src"
    fi
fi

if [ ! -f "$SOURCE/wobble/cli.py" ]; then
    fail "'$SOURCE' is not a Wobble source tree (wobble/cli.py missing)."
    exit 1
fi

# ---------------------------------------------------------------------------
# 2. Python 3
# ---------------------------------------------------------------------------
PYTHON=""
if command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
elif command -v python >/dev/null 2>&1; then
    PYTHON=python
fi

if [ -z "$PYTHON" ]; then
    warn "Python 3 not found."
    if command -v pkg >/dev/null 2>&1; then
        step "2/5" "Installing Python via Termux (pkg install -y python)..."
        pkg install -y python
        PYTHON=python3
    elif command -v apt-get >/dev/null 2>&1; then
        step "2/5" "Installing Python via apt-get..."
        apt-get update && apt-get install -y python3
        PYTHON=python3
    else
        fail "Python 3 is required. Install it manually and re-run this script."
        exit 1
    fi
else
    step "2/5" "Python 3: $("$PYTHON" --version 2>&1)"
fi

# ---------------------------------------------------------------------------
# 3. Install standalone runtime
# ---------------------------------------------------------------------------
step "3/5" "Installing runtime into $INSTALL_ROOT ..."

set -- self install --root "$INSTALL_ROOT" --bin "$BIN_DIR"
[ "$FORCE" = 1 ] && set -- "$@" --force
[ "$COMPLETIONS" = 0 ] && set -- "$@" --no-completion
[ "$UPDATE_PATH" = 0 ] && set -- "$@" --no-path
[ "$SNAPSHOT" = 0 ] && set -- "$@" --no-snapshot

# The shell script already printed the wordmark, and its final notes replace
# the Python handler's banner. Keep the rich install summary card.
if ! PYTHONPATH="$SOURCE" WOBBLE_INSTALL_QUIET=1 "$PYTHON" -m wobble.cli "$@"; then
    fail "Installation failed."
    exit 1
fi

# ---------------------------------------------------------------------------
# 4. Verify the standalone launcher
# ---------------------------------------------------------------------------
step "4/5" "Verifying standalone launcher..."
if "$BIN_DIR/wob" --version >/dev/null 2>&1; then
    ok "Launcher works: $("$BIN_DIR/wob" --version)"
else
    fail "'$BIN_DIR/wob' could not run. Check that Python 3 is available in PATH."
    exit 1
fi

if "$BIN_DIR/wob" --no-color self verify >/dev/null 2>&1; then
    ok "Runtime integrity verified (installed files match the manifest)"
else
    warn "Integrity check reported issues. Run: wob self verify"
fi

# ---------------------------------------------------------------------------
# 5. Final notes
# ---------------------------------------------------------------------------
step "5/5" "Installation complete."
printf '\n  %sThe source checkout is no longer needed.%s You may delete it safely.\n' "$BOLD" "$RESET"
printf '  Open a new terminal (or run %ssource ~/.bashrc%s), then:\n\n' "$BOLD" "$RESET"
printf '    %swob doctor%s        audit your environment\n' "$BOLD" "$RESET"
printf '    %swob create web demo%s\n' "$BOLD" "$RESET"
printf '    %swob self status%s    show install details\n' "$BOLD" "$RESET"
printf '    %swob uninstall%s      remove Wobble (projects are kept)\n' "$BOLD" "$RESET"
printf '    %swob rescue%s         emergency self-repair if wob ever breaks\n\n' "$BOLD" "$RESET"
