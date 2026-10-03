#!/usr/bin/env sh
# Wobble Uninstaller
# Safely removes Wobble executables and global configuration without deleting user projects.

set -e

RESET="\033[0m"
BOLD="\033[1m"
YELLOW="\033[33m"
GREEN="\033[32m"

echo "${BOLD}${YELLOW}Uninstalling Wobble CLI...${RESET}"

HOME_DIR="${HOME:-/data/data/com.termux/files/home}"
LOCAL_BIN="${HOME_DIR}/.local/bin"

# 1. Remove symlinks
if [ -L "${LOCAL_BIN}/wob" ] || [ -f "${LOCAL_BIN}/wob" ]; then
    rm -f "${LOCAL_BIN}/wob"
    echo "${GREEN}✓${RESET} Removed ${LOCAL_BIN}/wob"
fi

if [ -n "$PREFIX" ] && [ -e "$PREFIX/bin/wob" ]; then
    rm -f "$PREFIX/bin/wob"
    echo "${GREEN}✓${RESET} Removed $PREFIX/bin/wob"
fi

# 2. Ask or clean ~/.wobble
if [ -d "${HOME_DIR}/.wobble" ]; then
    rm -rf "${HOME_DIR}/.wobble"
    echo "${GREEN}✓${RESET} Cleaned ~/.wobble cache"
fi

if [ -d "${HOME_DIR}/.config/wobble" ]; then
    rm -rf "${HOME_DIR}/.config/wobble"
    echo "${GREEN}✓${RESET} Cleaned ~/.config/wobble settings"
fi

echo ""
echo "${BOLD}${GREEN}Wobble has been completely uninstalled.${RESET}"
echo "Your project directories have been preserved."
