"""Verified system-package names and install hints.

Wobble prints copy-paste install commands in ``wob doctor``, ``wob deps`` and
several error messages.  Historically those commands were hard-coded for
Termux, which broke in three ways:

* they were printed on Debian/Fedora/Arch hosts where ``pkg`` does not exist
  and the Debian package names differ (``openjdk-17`` vs ``openjdk-17-jdk``);
* they drifted from the real Termux repositories (``aapt2`` and ``zipalign``
  are shipped by the ``aapt`` package tree, ``aapt2`` as its own split
  package, and Termux has no Android SDK package at all);
* they silently aged out (Termux now ships ``openjdk-17``, ``openjdk-21`` and
  ``openjdk-25``, while ``openjdk-11`` has never been packaged).

This module is the single source of truth.  Every Termux name below was
checked against the package build scripts in ``termux/termux-packages``
(``packages/<name>/build.sh``).  The mapping is documented in
``docs/termux_packages.md`` together with the upstream evidence.

Keep it dependency-light: importing this module must not slow down startup.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from wobble.core.context import find_tool, is_termux

TERMUX = "termux"
APT = "apt"
DNF = "dnf"
PACMAN = "pacman"

#: Only families whose package names could be verified are listed here.  Other
#: managers (for example Alpine's apk) still count as "a package manager exists"
#: for the doctor, but Wobble will not invent package names for them.
FAMILY_LABELS = {
    TERMUX: "Termux pkg",
    APT: "apt",
    DNF: "dnf",
    PACMAN: "pacman",
}

# tool key -> family -> package names that provide it
PACKAGE_MAP: Dict[str, Dict[str, Tuple[str, ...]]] = {
    "git": {
        TERMUX: ("git",), APT: ("git",), DNF: ("git",), PACMAN: ("git",),
    },
    "python": {
        TERMUX: ("python",), APT: ("python3", "python3-pip"),
        DNF: ("python3", "python3-pip"), PACMAN: ("python", "python-pip"),
    },
    "nodejs": {
        TERMUX: ("nodejs",), APT: ("nodejs", "npm"), DNF: ("nodejs", "npm"),
        PACMAN: ("nodejs", "npm"),
    },
    "php": {
        TERMUX: ("php",), APT: ("php-cli",), DNF: ("php-cli",),
        PACMAN: ("php",),
    },
    # Termux ships openjdk-17, openjdk-21 and openjdk-25; 11 was never packaged.
    # The Android Gradle Plugin requires JDK 17 as its minimum, so 17 remains
    # the safest default.
    "jdk": {
        TERMUX: ("openjdk-17",), APT: ("openjdk-17-jdk",),
        DNF: ("java-17-openjdk-devel",), PACMAN: ("jdk17-openjdk",),
    },
    "gradle": {
        TERMUX: ("gradle",), APT: ("gradle",), DNF: ("gradle",),
        PACMAN: ("gradle",),
    },
    # Termux: "aapt" installs aapt and zipalign; aapt2 is a split package.
    "aapt": {TERMUX: ("aapt",)},
    "aapt2": {TERMUX: ("aapt2",)},
    "apksigner": {TERMUX: ("apksigner",)},
    "adb": {
        TERMUX: ("android-tools",), APT: ("adb",), DNF: ("android-tools",),
        PACMAN: ("android-tools",),
    },
    # termux-open, termux-am and termux-setup-storage live in termux-tools.
    "termux-tools": {TERMUX: ("termux-tools",)},
    "zip": {
        TERMUX: ("zip", "unzip"), APT: ("zip", "unzip"), DNF: ("zip", "unzip"),
        PACMAN: ("zip", "unzip"),
    },
}

INSTALL_TEMPLATES = {
    TERMUX: "pkg install -y {}",
    APT: "sudo apt install -y {}",
    DNF: "sudo dnf install -y {}",
    PACMAN: "sudo pacman -S --needed {}",
}

UPDATE_COMMANDS = {
    TERMUX: "pkg update",
    APT: "sudo apt update",
    DNF: "sudo dnf check-update",
    PACMAN: "sudo pacman -Sy",
}

# Packages that only exist inside Termux.  On other hosts the equivalent
# tooling comes from Google's Android SDK command-line tools instead.
TERMUX_ONLY = ("aapt", "aapt2", "apksigner", "termux-tools")

ANDROID_SDK_PACKAGES = ("platform-tools", "platforms;android-34", "build-tools;34.0.0")


def package_family() -> str:
    """Return the detected package-manager family (``termux``/``apt``/...)."""
    if is_termux():
        return TERMUX
    for family, tool in ((APT, "apt-get"), (DNF, "dnf"), (PACMAN, "pacman")):
        if find_tool(tool):
            return family
    return ""


def family_label(family: Optional[str] = None) -> str:
    return FAMILY_LABELS.get(family or package_family(), "your package manager")


def packages_for(keys: Iterable[str], family: Optional[str] = None) -> List[str]:
    """Resolve tool keys to package names for *family*, de-duplicated and ordered."""
    fam = family or package_family()
    resolved: List[str] = []
    for key in keys:
        for name in PACKAGE_MAP.get(key, {}).get(fam, ()):
            if name not in resolved:
                resolved.append(name)
    return resolved


def unsupported_keys(keys: Iterable[str], family: Optional[str] = None) -> List[str]:
    """Tool keys that have no package in *family* (usually Android build tools)."""
    fam = family or package_family()
    return [key for key in keys if not PACKAGE_MAP.get(key, {}).get(fam)]


def install_argv(keys: Iterable[str], family: Optional[str] = None) -> List[str]:
    """Build an install command array for the detected package manager."""
    fam = family or package_family()
    names = packages_for(keys, fam)
    if not names:
        return []
    if fam == TERMUX:
        return ["pkg", "install", "-y"] + names
    if fam == APT:
        return ["apt-get", "install", "-y"] + names
    if fam == DNF:
        return ["dnf", "install", "-y"] + names
    if fam == PACMAN:
        return ["pacman", "-S", "--needed", "--noconfirm"] + names
    return []


def install_command(keys: Iterable[str], family: Optional[str] = None) -> Optional[str]:
    """Return a copy-paste install command, or ``None`` when nothing applies."""
    fam = family or package_family()
    names = packages_for(keys, fam)
    if not names:
        return None
    template = INSTALL_TEMPLATES.get(fam)
    if not template:
        return None
    return template.format(" ".join(names))


def update_command(family: Optional[str] = None) -> Optional[str]:
    return UPDATE_COMMANDS.get(family or package_family())


def install_hint(keys: Sequence[str], prefix: str = "") -> Optional[str]:
    """Full sentence for a doctor/deps ``fix`` field.

    Falls back to the Android SDK instructions when the requested tools are not
    packaged on this platform, instead of printing a Termux-only command.
    """
    fam = family_label()
    command = install_command(keys)
    missing = unsupported_keys(keys)
    if command:
        text = f"{prefix}{command}".strip()
        if missing:
            text += "  (plus the Android SDK build-tools below)"
        return text
    if missing:
        # A full sentence replaces the "Install X with:" prefix, otherwise the
        # advice reads "Install Android build tools: Install Google's ...".
        return (f"Google's Android build-tools are not packaged for {fam}; install "
                f"them with sdkmanager (see 'wob deps install android-sdk').")
    return None


def android_sdk_hint() -> str:
    """Honest instructions for obtaining the Android SDK (no distro package)."""
    return ("Install Google's Android command-line tools, accept the licences with "
            "'yes | sdkmanager --licenses', then run "
            "'sdkmanager \"platform-tools\" \"platforms;android-34\" \"build-tools;34.0.0\"'.")


def is_termux_only(key: str) -> bool:
    return key in TERMUX_ONLY
