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
                "reality": "Android 10 removes execute permission for files in an app's writable home directory when the app targets API 29 or higher (W^X), and Android's shared/external storage does not support executables at all. Termux sidesteps the first rule by targeting API 28 and executes binaries from its private rootfs ($PREFIX).",
                "solution": "All development binaries and toolchains must reside in $PREFIX/bin, $HOME/.local/bin or another private directory. Wobble never executes code from /sdcard or ~/storage.",
                "status": "enforced_by_os"
            },
            {
                "topic": "Phantom Process Killer & RAM Constraints",
                "reality": "Android 12+ runs a phantom-process killer that terminates an app's unmanaged child processes once more than 32 of them exist, and the low-memory killer can still reclaim large JVMs under memory pressure.",
                "solution": "Wobble configures Gradle with --no-daemon, sets JVM heap to -Xmx1024m, and disables parallel workers by default to prevent OOM termination.",
                "status": "mitigated"
            },
            {
                "topic": "Android SDK Availability",
                "reality": "Google's Android SDK command-line tools are published for x86_64 Linux, not for Android itself. Termux packages aapt, aapt2, apksigner and OpenJDK natively, but nothing in Termux or in a Linux distribution provides the SDK platforms and build-tools that Gradle expects.",
                "solution": "Install Google's command-line tools (or a trusted ARM64 port), accept the licences and fetch packages with 'sdkmanager'. 'wob deps install android-sdk' does this for you once sdkmanager is on PATH, and 'wob doctor' reports which platforms and build-tools were detected.",
                "status": "handled_with_sdk"
            },
            {
                "topic": "Release APK Signing",
                "reality": "Android requires all APKs to be cryptographically signed before installation. Unsigned APKs are rejected by the Android Package Installer.",
                "solution": "Debug builds are automatically signed with Android's default debug keystore. Release builds require an explicit keystore or apksigner configuration.",
                "status": "handled_automatically"
            }
        ]
    }
