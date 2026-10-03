"""
Wobble Environment Doctor
Inspects system architecture, Android version, Termux setup, SDK, JDK, web tools,
and provides practical, actionable fixes for every detected issue.
"""

import os
import sys
import shutil
import platform
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from wobble.core.context import (
    is_termux,
    get_prefix,
    get_home,
    get_architecture,
    get_android_version,
    get_termux_version,
    get_storage_info,
    get_memory_info,
    get_android_sdk_candidates,
    get_java_home_candidates,
    find_tool,
    get_lan_ip
)
from wobble.core.executor import run_command


class CheckResult:
    def __init__(
        self,
        name: str,
        category: str,
        status: str,  # "ok", "warning", "missing", "error"
        details: str = "",
        problem: Optional[str] = None,
        fix: Optional[str] = None
    ):
        self.name = name
        self.category = category
        self.status = status
        self.details = details
        self.problem = problem
        self.fix = fix

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "status": self.status,
            "details": self.details,
            "problem": self.problem,
            "fix": self.fix
        }


def check_tool_version(cmd: List[str], version_flag: str = "--version", timeout: int = 5) -> Tuple[bool, str]:
    """Helper to run a tool and extract its first version output line."""
    try:
        res = run_command([cmd[0], version_flag], timeout=timeout)
        if res.success:
            first_line = (res.stdout or res.stderr).strip().splitlines()[0]
            return True, first_line
        # Some tools output version to stderr or exit non-zero
        out = (res.stdout or res.stderr).strip()
        if out:
            return True, out.splitlines()[0]
    except Exception:
        pass
    return False, ""


def inspect_environment() -> List[CheckResult]:
    """Run all diagnostic checks across the system."""
    results: List[CheckResult] = []

    # 1. Environment & Architecture
    arch = get_architecture()
    results.append(CheckResult(
        name="CPU Architecture",
        category="System",
        status="ok" if arch in ("aarch64", "arm", "x86_64") else "warning",
        details=f"{arch} ({platform.machine()})",
        problem=f"Uncommon architecture: {arch}" if arch not in ("aarch64", "arm", "x86_64") else None,
        fix="Termux development works best on aarch64 (ARM64). Some binary tools might need compilation." if arch not in ("aarch64", "arm", "x86_64") else None
    ))

    in_termux = is_termux()
    results.append(CheckResult(
        name="Termux Environment",
        category="System",
        status="ok" if in_termux else "warning",
        details=f"Prefix: {get_prefix()}" if in_termux else "Running outside standard Termux",
        problem=None if in_termux else "Not detected as running inside Termux environment.",
        fix=None if in_termux else "Ensure $PREFIX is set or run directly inside the Termux app."
    ))

    t_ver = get_termux_version()
    results.append(CheckResult(
        name="Termux Version",
        category="System",
        status="ok" if t_ver else "warning",
        details=t_ver or "Could not detect exact version",
        problem=None if t_ver else "Termux version string not found in environment or dpkg.",
        fix=None if t_ver else "Make sure you installed Termux from F-Droid or GitHub Releases, NOT Google Play Store (which is deprecated)."
    ))

    android_info = get_android_version()
    rel = android_info.get("release")
    api = android_info.get("api_level")
    device = f"{android_info.get('brand', '')} {android_info.get('model', '')}".strip()
    if rel:
        details_str = f"Android {rel} (API {api or 'unknown'})"
        if device:
            details_str += f" - {device}"
        results.append(CheckResult(
            name="Android Version",
            category="System",
            status="ok",
            details=details_str
        ))
    else:
        results.append(CheckResult(
            name="Android Version",
            category="System",
            status="warning",
            details="Could not query Android getprop",
            problem="Android system properties not accessible.",
            fix="Usually harmless if running inside Termux proot or container."
        ))

    # 2. Storage & Memory
    storage = get_storage_info()
    if "error" not in storage:
        free_bytes = storage.get("free_bytes", 0)
        # Warn if less than 1.5 GB free
        low_storage = free_bytes < (1.5 * 1024 * 1024 * 1024)
        results.append(CheckResult(
            name="Available Storage",
            category="Resources",
            status="warning" if low_storage else "ok",
            details=f"{storage['free_human']} free of {storage['total_human']} ({storage['percent_used']}% used)",
            problem="Low disk storage. Gradle builds and Android SDK can consume multiple gigabytes." if low_storage else None,
            fix="Clean up unused files with 'pkg clean', 'wob clean', or remove old caches." if low_storage else None
        ))

    mem = get_memory_info()
    if "error" not in mem:
        avail_bytes = mem.get("available_bytes", 0)
        low_mem = avail_bytes < (500 * 1024 * 1024)
        results.append(CheckResult(
            name="System Memory",
            category="Resources",
            status="warning" if low_mem else "ok",
            details=f"{mem['available_human']} available of {mem['total_human']}",
            problem="Low available RAM. Heavy Gradle compilations or Node builds might trigger OOM killer." if low_mem else None,
            fix="Close background apps or increase swap space/zram if your device supports it." if low_mem else None
        ))

    # 3. Termux Permissions & PATH
    path_env = os.environ.get("PATH", "")
    prefix_bin = str(get_prefix() / "bin")
    home_local_bin = str(get_home() / ".local" / "bin")
    path_ok = prefix_bin in path_env
    results.append(CheckResult(
        name="PATH Configuration",
        category="Environment",
        status="ok" if path_ok else "warning",
        details="Standard PATH active" if path_ok else f"Missing {prefix_bin} in PATH",
        problem=f"{prefix_bin} is not in PATH." if not path_ok else None,
        fix=f"Add export PATH=\"{prefix_bin}:{home_local_bin}:$PATH\" to ~/.bashrc" if not path_ok else None
    ))

    storage_dir = get_home() / "storage"
    results.append(CheckResult(
        name="Android Storage Access",
        category="Environment",
        status="ok" if storage_dir.exists() else "warning",
        details="Access granted (~/storage exists)" if storage_dir.exists() else "Not set up",
        problem="Termux storage permission has not been granted. Cannot easily export APKs to shared storage / Download folder." if not storage_dir.exists() else None,
        fix="Run 'termux-setup-storage' in Termux and grant permission." if not storage_dir.exists() else None
    ))

    # 4. Core Development Tools
    # Git
    git_bin = find_tool("git")
    if git_bin:
        ok, v = check_tool_version([git_bin], "--version")
        results.append(CheckResult(
            name="Git",
            category="Dev Tools",
            status="ok",
            details=v or git_bin
        ))
    else:
        results.append(CheckResult(
            name="Git",
            category="Dev Tools",
            status="missing",
            details="Not installed",
            problem="Git is required to clone templates, plugins, and manage project version control.",
            fix="Install Git with: pkg install -y git"
        ))

    # Python
    py_bin = find_tool("python3") or find_tool("python")
    if py_bin:
        ok, v = check_tool_version([py_bin], "--version")
        results.append(CheckResult(
            name="Python",
            category="Dev Tools",
            status="ok",
            details=v or py_bin
        ))
    else:
        results.append(CheckResult(
            name="Python",
            category="Dev Tools",
            status="missing",
            details="Not installed",
            problem="Python 3 is recommended for running Wobble core, scripts, and Python web projects.",
            fix="Install Python with: pkg install -y python"
        ))

    # Node.js
    node_bin = find_tool("node")
    npm_bin = find_tool("npm")
    if node_bin:
        ok, v = check_tool_version([node_bin], "--version")
        results.append(CheckResult(
            name="Node.js",
            category="Web Tools",
            status="ok",
            details=v or node_bin
        ))
    else:
        results.append(CheckResult(
            name="Node.js",
            category="Web Tools",
            status="missing",
            details="Not installed",
            problem="Node.js is required for Vite, React, Vue, Svelte, and modern web frameworks.",
            fix="Install Node.js with: pkg install -y nodejs"
        ))

    if npm_bin:
        ok, v = check_tool_version([npm_bin], "--version")
        results.append(CheckResult(
            name="npm",
            category="Web Tools",
            status="ok",
            details=v or npm_bin
        ))
    else:
        results.append(CheckResult(
            name="npm",
            category="Web Tools",
            status="missing" if not node_bin else "warning",
            details="Not installed",
            problem="npm package manager is needed to install web project dependencies.",
            fix="Install npm (included with nodejs) or run: pkg install -y nodejs"
        ))

    # PHP
    php_bin = find_tool("php")
    if php_bin:
        ok, v = check_tool_version([php_bin], "--version")
        results.append(CheckResult(
            name="PHP",
            category="Web Tools",
            status="ok",
            details=v.splitlines()[0] if v else php_bin
        ))
    else:
        results.append(CheckResult(
            name="PHP",
            category="Web Tools",
            status="missing",
            details="Not installed (optional)",
            problem="PHP is required only if you develop PHP web applications or APIs.",
            fix="Install PHP with: pkg install -y php"
        ))

    # 5. Android Development Toolchain
    # Java / JDK
    java_bin = find_tool("java")
    javac_bin = find_tool("javac")
    if java_bin:
        ok, v = check_tool_version([java_bin], "-version")
        jdk_details = v or java_bin
        if javac_bin:
            jdk_details += " (JDK compiler present)"
        results.append(CheckResult(
            name="Java / JDK",
            category="Android Toolchain",
            status="ok" if javac_bin else "warning",
            details=jdk_details,
            problem=None if javac_bin else "Java runtime found, but javac compiler is missing.",
            fix=None if javac_bin else "Install full JDK with: pkg install -y openjdk-17"
        ))
    else:
        results.append(CheckResult(
            name="Java / JDK",
            category="Android Toolchain",
            status="missing",
            details="Not installed",
            problem="Java JDK is required to build Android APKs using Gradle.",
            fix="Install OpenJDK 17 with: pkg install -y openjdk-17"
        ))

    # Gradle
    gradle_bin = find_tool("gradle")
    if gradle_bin:
        ok, v = check_tool_version([gradle_bin], "--version")
        results.append(CheckResult(
            name="Gradle",
            category="Android Toolchain",
            status="ok",
            details=v or gradle_bin
        ))
    else:
        results.append(CheckResult(
            name="Gradle",
            category="Android Toolchain",
            status="missing",
            details="Not installed globally (gradlew can be used inside projects)",
            problem="Global gradle command not installed. Note: projects with gradlew wrapper can still build.",
            fix="Install Gradle with: pkg install -y gradle"
        ))

    # Android SDK
    sdk_candidates = get_android_sdk_candidates()
    if sdk_candidates:
        sdk_path = sdk_candidates[0]
        # Inspect what is inside SDK
        has_platforms = (sdk_path / "platforms").exists() and any((sdk_path / "platforms").iterdir())
        has_build_tools = (sdk_path / "build-tools").exists() and any((sdk_path / "build-tools").iterdir())
        has_cmdline = (sdk_path / "cmdline-tools").exists()

        status = "ok" if (has_platforms and has_build_tools) else "warning"
        details_list = [f"Path: {sdk_path}"]
        if has_platforms:
            details_list.append("Platforms: ✓")
        else:
            details_list.append("Platforms: missing")
        if has_build_tools:
            details_list.append("Build-tools: ✓")
        else:
            details_list.append("Build-tools: missing")

        results.append(CheckResult(
            name="Android SDK",
            category="Android Toolchain",
            status=status,
            details=" | ".join(details_list),
            problem="Android SDK is missing platforms or build-tools." if status != "ok" else None,
            fix="Install SDK packages via sdkmanager or run 'wob deps install android-sdk'." if status != "ok" else None
        ))
    else:
        results.append(CheckResult(
            name="Android SDK",
            category="Android Toolchain",
            status="missing",
            details="Not found in standard paths or $ANDROID_HOME",
            problem="Android SDK is required to compile native Android applications on Termux.",
            fix="Set ANDROID_HOME in ~/.bashrc or run 'wob deps install android-sdk'."
        ))

    # Android Build Tools (aapt / aapt2 / apksigner / zipalign)
    aapt2_bin = find_tool("aapt2") or find_tool("aapt")
    apksigner_bin = find_tool("apksigner")
    zipalign_bin = find_tool("zipalign")
    btools_found = []
    if aapt2_bin:
        btools_found.append("aapt2")
    if apksigner_bin:
        btools_found.append("apksigner")
    if zipalign_bin:
        btools_found.append("zipalign")

    if len(btools_found) >= 2:
        results.append(CheckResult(
            name="Android Build Tools",
            category="Android Toolchain",
            status="ok",
            details=", ".join(btools_found)
        ))
    else:
        results.append(CheckResult(
            name="Android Build Tools",
            category="Android Toolchain",
            status="warning" if btools_found else "missing",
            details=", ".join(btools_found) if btools_found else "aapt2, apksigner, zipalign not found",
            problem="Android build packaging utilities (aapt2, apksigner, zipalign) are needed to inspect or package APKs directly.",
            fix="Install Android build tools: pkg install -y aapt apksigner"
        ))

    # ADB (Android Debug Bridge)
    adb_bin = find_tool("adb")
    if adb_bin:
        ok, v = check_tool_version([adb_bin], "version")
        results.append(CheckResult(
            name="ADB (Android Debug Bridge)",
            category="Android Toolchain",
            status="ok",
            details=v or adb_bin
        ))
    else:
        results.append(CheckResult(
            name="ADB (Android Debug Bridge)",
            category="Android Toolchain",
            status="missing",
            details="Not installed (optional on-device)",
            problem="ADB is optional when running on the device itself. Wobble can install APKs directly via Android's package installer.",
            fix="To enable ADB over Wi-Fi / localhost: pkg install -y android-tools"
        ))

    return results


def run_doctor(json_mode: bool = False) -> Dict[str, Any]:
    """Run doctor and render output or return JSON dictionary."""
    results = inspect_environment()

    counts = {"ok": 0, "warning": 0, "missing": 0, "error": 0}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1

    report_data = {
        "status": "healthy" if counts["missing"] == 0 and counts["error"] == 0 else "needs_attention",
        "counts": counts,
        "checks": [r.to_dict() for r in results],
        "lan_ip": get_lan_ip()
    }

    if json_mode:
        import json
        print(json.dumps(report_data, indent=2))
        return report_data

    # Human-readable rendering
    print("\n" + "=" * 58)
    print("           WOBBLE ENVIRONMENT DOCTOR")
    print("=" * 58)

    current_cat = ""
    for r in results:
        if r.category != current_cat:
            current_cat = r.category
            print(f"\n[ {current_cat} ]")

        if r.status == "ok":
            icon = "\033[32m✓\033[0m"
        elif r.status == "warning":
            icon = "\033[33m⚠\033[0m"
        elif r.status == "missing":
            icon = "\033[31m✗\033[0m"
        else:
            icon = "\033[31m!\033[0m"

        print(f"  {icon} {r.name:<26} {r.details}")
        if r.problem:
            print(f"      \033[2mProblem:\033[0m {r.problem}")
        if r.fix:
            print(f"      \033[36mFix:\033[0m {r.fix}")

    print("\n" + "-" * 58)
    print(f"Summary: \033[32m{counts['ok']} Passed\033[0m | "
          f"\033[33m{counts['warning']} Warnings\033[0m | "
          f"\033[31m{counts['missing']} Missing\033[0m")

    if counts["missing"] > 0 or counts["warning"] > 0:
        print("\n\033[1mQuick Fix Recommendations:\033[0m")
        suggested_pkg = []
        if any(r.name == "Git" and r.status == "missing" for r in results):
            suggested_pkg.append("git")
        if any(r.name == "Node.js" and r.status == "missing" for r in results):
            suggested_pkg.append("nodejs")
        if any(r.name == "Java / JDK" and r.status == "missing" for r in results):
            suggested_pkg.append("openjdk-17")
        if any(r.name == "Android Build Tools" and r.status == "missing" for r in results):
            suggested_pkg.append("aapt")
        if suggested_pkg:
            print(f"  pkg install -y {' '.join(suggested_pkg)}")

    print("=" * 58 + "\n")
    return report_data
