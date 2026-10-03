"""
Wobble Android & Termux Limitations Reporter
Provides honest, technical documentation of Android OS constraints, Termux boundaries,
and reliable workarounds.
"""

from typing import Dict, List, Any


def get_android_limitations_report() -> Dict[str, Any]:
    """Return structured report of Android and Termux limitations and best practices."""
    return {
        "title": "Android & Termux Technical Limitations",
        "philosophy": "Honest capabilities without root or fake claims",
        "principles": [
            "Root is NOT required and never assumed.",
            "Shizuku is NOT required and never assumed.",
            "ADB is optional; on-device development uses standard Android Intents."
        ],
        "limitations": [
            {
                "topic": "APK Installation on Device",
                "reality": "Non-root Android applications cannot silently install packages in the background.",
                "solution": "Wobble uses 'termux-open <apk>' or 'am start' to trigger Android's system Package Installer prompt. The user confirms installation with a single tap on the Android prompt.",
                "status": "fully_supported"
            },
            {
                "topic": "W^X (Write XOR Execute) & execve Constraints",
                "reality": "Android 10+ SELinux prevents executing binaries stored on shared/external storage (/sdcard) or writable storage outside app private binaries.",
                "solution": "All development binaries and toolchains must reside in $PREFIX/bin or $HOME/.local/bin. Wobble ensures project build scripts run from Termux private storage.",
                "status": "enforced_by_os"
            },
            {
                "topic": "Phantom Process Killer & RAM Constraints",
                "reality": "Android 12+ limits background child processes to 32 total and terminates processes that consume excessive RAM or background CPU.",
                "solution": "Wobble configures Gradle with --no-daemon, sets JVM heap to -Xmx1024m, and disables parallel workers by default to prevent OOM termination.",
                "status": "mitigated"
            },
            {
                "topic": "Android SDK & 32-bit/64-bit Binaries",
                "reality": "Google's official SDK commandline-tools are distributed primarily for x86_64 Linux. On ARM64 Android, standard aapt/aapt2, ecj, and dx/d8 binaries compiled natively for Termux must be used.",
                "solution": "Wobble detects native Termux aapt and openjdk packages, and configures build systems to use native Termux toolchain binaries.",
                "status": "handled_automatically"
            },
            {
                "topic": "Release APK Signing",
                "reality": "Android requires all APKs to be cryptographically signed before installation. Unsigned APKs are rejected by the Android Package Installer.",
                "solution": "Debug builds are automatically signed with Android's default debug keystore. Release builds require an explicit keystore or apksigner configuration.",
                "status": "handled_automatically"
            }
        ]
    }
