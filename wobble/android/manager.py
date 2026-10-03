"""
Wobble Android Project Workflow Coordinator
Coordinates Gradle builds, clean commands, APK discovery, and status reporting.
"""

from pathlib import Path
from typing import Dict, Any, Optional

from wobble.core.logger import get_logger
from wobble.core.executor import run_command, stream_command
from wobble.plugins.loader import get_plugin
from wobble.android.apk import find_apks, inspect_apk
from wobble.android.sdk import get_sdk_status


def build_android(project_path: Path, release: bool = False, clean: bool = False) -> Dict[str, Any]:
    """Execute Android build using the Android framework plugin or Gradle."""
    logger = get_logger()
    android_plugin = get_plugin("android")

    if not android_plugin:
        return {"success": False, "error": "Android plugin not available"}

    if clean:
        logger.step("Cleaning prior build artifacts...")
        clean_cmd = android_plugin.get_clean_command(project_path)
        if clean_cmd:
            run_command(clean_cmd, cwd=project_path)

    cmd = android_plugin.get_build_command(project_path, {"release": release})
    if not cmd:
        return {"success": False, "error": "Could not determine Gradle build command"}

    mode = "Release" if release else "Debug"
    logger.step(f"Starting Android {mode} build with Gradle ({' '.join(cmd)})...")

    # Stream output during build
    exit_code = stream_command(cmd, cwd=project_path)
    if exit_code != 0:
        logger.error(f"Gradle build failed with exit code {exit_code}")
        return {
            "success": False,
            "exit_code": exit_code,
            "error": f"Gradle build failed with exit code {exit_code}"
        }

    # Find generated APKs
    apks = find_apks(project_path)
    latest_apk_info = None
    if apks:
        latest_apk_info = inspect_apk(apks[0])
        logger.success(f"Built APK successfully: {apks[0].name} ({latest_apk_info.get('size_human', '')})")

    return {
        "success": True,
        "exit_code": 0,
        "mode": mode.lower(),
        "apks": [str(a) for a in apks],
        "latest_apk": latest_apk_info
    }


def clean_android(project_path: Path) -> Dict[str, Any]:
    """Clean Android project build files."""
    android_plugin = get_plugin("android")
    if not android_plugin:
        return {"success": False, "error": "Android plugin not found"}

    cmd = android_plugin.get_clean_command(project_path)
    if not cmd:
        return {"success": False, "error": "No clean command defined"}

    res = run_command(cmd, cwd=project_path)
    return {
        "success": res.success,
        "stdout": res.stdout,
        "stderr": res.stderr
    }
