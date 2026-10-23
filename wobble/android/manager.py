"""
Wobble Android Project Workflow Coordinator
Coordinates Gradle builds, clean commands, APK discovery, and status reporting.
"""

from pathlib import Path
from typing import Dict, Any, Optional

from wobble.core.logger import get_logger
from wobble.core.executor import run_command, stream_command_result
from wobble.plugins.loader import get_plugin
from wobble.android.apk import find_apks, inspect_apk
from wobble.android.sdk import get_sdk_status


def build_android(project_path: Path, release: bool = False, clean: bool = False) -> Dict[str, Any]:
    """Execute Android build using the Android framework plugin or Gradle."""
    logger = get_logger()
    android_plugin = get_plugin("android")

    if not android_plugin:
        return {"success": False, "error": "Android plugin not available"}

    # Fail with a diagnosis instead of a Gradle stack trace when the installed
    # Gradle cannot run the AGP the project pins (Termux now ships Gradle 9.x,
    # while the scaffold's AGP 8.x line targets Gradle 8.13).
    compat_check = getattr(android_plugin, "gradle_compatibility_problem", None)
    compat = compat_check(project_path) if compat_check else None
    if compat:
        return {
            "success": False,
            "error": f"Gradle cannot build this project: {compat['reason']}.",
            "error_code": "gradle_agp_incompatible",
            "hint": compat["hint"],
            "details": {"agp": compat["agp"], "gradle": compat["gradle"]},
        }

    if clean:
        logger.step("Cleaning prior build artifacts...")
        clean_cmd = android_plugin.get_clean_command(project_path)
        if clean_cmd:
            clean_result = run_command(clean_cmd, cwd=project_path)
            if not clean_result.success:
                failure = clean_result.to_dict()
                failure["error"] = f"Gradle clean failed: {clean_result.error}"
                failure["stage"] = "clean"
                return failure

    cmd = android_plugin.get_build_command(project_path, {"release": release})
    if not cmd:
        return {"success": False, "error": "Could not determine Gradle build command"}

    mode = "Release" if release else "Debug"
    logger.step(f"Starting Android {mode} build with Gradle ({' '.join(cmd)})...")

    # Stream for humans; capture in JSON mode so Gradle output cannot corrupt
    # the machine-readable document.
    result = stream_command_result(
        cmd, cwd=project_path, capture_output=logger.json_mode
    )
    if not result.success:
        logger.error(f"Gradle build failed with exit code {result.returncode}: {result.error}")
        failure = result.to_dict()
        failure["exit_code"] = result.returncode
        failure["error"] = f"Gradle build failed with exit code {result.returncode}: {result.error}"
        failure["stage"] = "build"
        return failure

    # Find generated APKs
    apks = find_apks(project_path)
    latest_apk_info = None
    if apks:
        latest_apk_info = inspect_apk(apks[0])
        logger.success(f"Built APK successfully: {apks[0].name} ({latest_apk_info.get('size_human', '')})")

    data = {
        "success": True,
        "exit_code": 0,
        "mode": mode.lower(),
        "apks": [str(a) for a in apks],
        "latest_apk": latest_apk_info
    }
    if not apks:
        # Gradle can exit 0 while a custom output path leaves nothing in the
        # standard directories; say so instead of implying an APK exists.
        data["warning"] = ("Gradle reported success but no APK was found in the "
                          "standard output directories.")
        logger.warn("Gradle finished, but no APK was found under app/build/outputs.")
    return data


def clean_android(project_path: Path) -> Dict[str, Any]:
    """Clean Android project build files."""
    android_plugin = get_plugin("android")
    if not android_plugin:
        return {"success": False, "error": "Android plugin not found"}

    cmd = android_plugin.get_clean_command(project_path)
    if not cmd:
        return {"success": False, "error": "No clean command defined"}

    res = run_command(cmd, cwd=project_path)
    return res.to_dict()
