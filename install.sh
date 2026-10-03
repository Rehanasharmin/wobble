#!/data/data/com.termux/files/usr/bin/sh
# Wobble Installer for Termux on Android
# "Termux -> Wobble -> Projects -> Frameworks -> Build -> Test -> APK/Web app"

set -e

RESET="\033[0m"
BOLD="\033[1m"
GREEN="\033[32m"
BLUE="\033[34m"
YELLOW="\033[33m"
RED="\033[31m"

echo "${BOLD}${BLUE}======================================================${RESET}"
echo "${BOLD}           Installing Wobble Development Harness      ${RESET}"
echo "${BOLD}${BLUE}======================================================${RESET}"

# 1. Environment & Architecture Detection
ARCH=$(uname -m 2>/dev/null || echo "unknown")
echo "${BLUE}➜${RESET} Detected Architecture: ${BOLD}${ARCH}${RESET}"

IS_TERMUX=false
if [ -n "$TERMUX_VERSION" ] || [ -d "/data/data/com.termux/files/usr" ]; then
    IS_TERMUX=true
    echo "${GREEN}✓${RESET} Detected Termux runtime environment"
else
    echo "${YELLOW}⚠${RESET} Running outside standard Termux (Linux compatibility mode)"
fi

# 2. Prerequisites Check
echo "${BLUE}➜${RESET} Checking core prerequisites..."

if ! command -v python3 >/dev/null 2>&1 && ! command -v python >/dev/null 2>&1; then
    if [ "$IS_TERMUX" = true ] && command -v pkg >/dev/null 2>&1; then
        echo "${YELLOW}ℹ${RESET} Python 3 not found. Installing via 'pkg install -y python'..."
        pkg install -y python
    else
        echo "${RED}✗ Error:${RESET} Python 3 is required. Please install python3."
        exit 1
    fi
fi
echo "${GREEN}✓${RESET} Python 3 verified"

# 3. Determine installation locations
HOME_DIR="${HOME:-/data/data/com.termux/files/home}"
LOCAL_BIN="${HOME_DIR}/.local/bin"
TARGET_DIR="${HOME_DIR}/wobble"
CURRENT_SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)

mkdir -p "${LOCAL_BIN}"
mkdir -p "${HOME_DIR}/.wobble"

REPO_URL="https://github.com/Rehanasharmin/wobble.git"

# If running installer from cloned repository, use this repository, otherwise clone into TARGET_DIR
if [ -f "${CURRENT_SCRIPT_DIR}/bin/wob" ]; then
    WOB_EXECUTABLE="${CURRENT_SCRIPT_DIR}/bin/wob"
    SCRIPT_ROOT="${CURRENT_SCRIPT_DIR}"
else
    if [ ! -d "${TARGET_DIR}" ] || [ ! -f "${TARGET_DIR}/bin/wob" ]; then
        echo "${BLUE}➜${RESET} Downloading Wobble repository to ${TARGET_DIR}..."
        if ! command -v git >/dev/null 2>&1; then
            if [ "$IS_TERMUX" = true ] && command -v pkg >/dev/null 2>&1; then
                echo "${YELLOW}ℹ${RESET} Installing git..."
                pkg install -y git
            fi
        fi
        git clone "${REPO_URL}" "${TARGET_DIR}"
    fi
    WOB_EXECUTABLE="${TARGET_DIR}/bin/wob"
    SCRIPT_ROOT="${TARGET_DIR}"
fi

chmod +x "${WOB_EXECUTABLE}"
chmod +x "${SCRIPT_ROOT}/uninstall.sh" 2>/dev/null || true
chmod +x "${SCRIPT_ROOT}/tests/run_tests.py" 2>/dev/null || true

# 4. Create Symlink in ~/.local/bin
echo "${BLUE}➜${RESET} Linking executable to ${LOCAL_BIN}/wob..."
rm -f "${LOCAL_BIN}/wob"
ln -sf "${WOB_EXECUTABLE}" "${LOCAL_BIN}/wob"
chmod +x "${LOCAL_BIN}/wob" 2>/dev/null || true
echo "${GREEN}✓${RESET} Linked 'wob' to ${LOCAL_BIN}/wob"

# Also link into $PREFIX/bin if writable
if [ -n "$PREFIX" ] && [ -w "$PREFIX/bin" ]; then
    ln -sf "${WOB_EXECUTABLE}" "$PREFIX/bin/wob" 2>/dev/null || true
    chmod +x "$PREFIX/bin/wob" 2>/dev/null || true
    echo "${GREEN}✓${RESET} Linked 'wob' to ${PREFIX}/bin/wob"
fi

# 5. Configure PATH in shell config safely without overwriting
update_shell_config() {
    CONF_FILE="$1"
    if [ -f "$CONF_FILE" ]; then
        if ! grep -q '\.local/bin' "$CONF_FILE"; then
            echo "" >> "$CONF_FILE"
            echo '# Wobble CLI PATH' >> "$CONF_FILE"
            echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$CONF_FILE"
            echo "${GREEN}✓${RESET} Added ~/.local/bin to $CONF_FILE"
        fi
    fi
}

update_shell_config "${HOME_DIR}/.bashrc"
update_shell_config "${HOME_DIR}/.zshrc"

export PATH="${LOCAL_BIN}:$PATH"

# 6. Verify Installation
echo "${BLUE}➜${RESET} Verifying Wobble installation..."
if "${LOCAL_BIN}/wob" --version >/dev/null 2>&1; then
    VER=$("${LOCAL_BIN}/wob" --version)
    echo "${GREEN}✓${RESET} Installation verified: ${BOLD}${VER}${RESET}"
else
    echo "${YELLOW}⚠${RESET} Note: PATH will take effect in new terminal sessions."
fi

echo ""
echo "${BOLD}${GREEN}======================================================${RESET}"
echo "${BOLD}${GREEN}           Wobble Successfully Installed!             ${RESET}"
echo "${BOLD}${GREEN}======================================================${RESET}"
echo ""
echo "Get started right away:"
echo "  1. Check system diagnostics:"
echo "     ${BOLD}wob doctor${RESET}"
echo ""
echo "  2. Create your first project:"
echo "     ${BOLD}wob create android myapp${RESET}   # Native Android App"
echo "     ${BOLD}wob create web mysite${RESET}      # Modern Web Application"
echo ""
echo "  3. Start developing:"
echo "     ${BOLD}cd mysite && wob web preview${RESET}"
echo ""
echo "For AI coding agents: run ${BOLD}wob schema${RESET} or read ${BOLD}AI_GUIDE.md${RESET}."
echo ""
