"""
Wobble Android SDK & Toolchain Manager
Detects SDK directories, installed platforms, build tools, and handles sdkmanager interactions.
"""

from pathlib import Path
from typing import Dict, Any, List, Optional

from wobble.core.context import get_android_sdk_candidates, find_tool
from wobble.core.executor import run_command


def get_sdk_status() -> Dict[str, Any]:
    """Inspect and report on installed Android SDK components."""
    candidates = get_android_sdk_candidates()
    if not candidates:
        return {
            "found": False,
            "path": None,
            "platforms": [],
            "build_tools": [],
            "has_cmdline_tools": False
        }

    sdk_path = candidates[0]
    platforms_dir = sdk_path / "platforms"
    build_tools_dir = sdk_path / "build-tools"
    cmdline_dir = sdk_path / "cmdline-tools"

    platforms = []
    if platforms_dir.is_dir():
        platforms = [p.name for p in platforms_dir.iterdir() if p.is_dir()]

    build_tools = []
    if build_tools_dir.is_dir():
        build_tools = [b.name for b in build_tools_dir.iterdir() if b.is_dir()]

    has_cmdline = cmdline_dir.is_dir() and any(cmdline_dir.iterdir())

    return {
        "found": True,
        "path": str(sdk_path),
        "platforms": sorted(platforms),
        "build_tools": sorted(build_tools),
        "has_cmdline_tools": has_cmdline
    }


def find_sdkmanager() -> Optional[str]:
    """Locate sdkmanager executable."""
    tool = find_tool("sdkmanager")
    if tool:
        return tool

    for candidate in get_android_sdk_candidates():
        for sub in ["cmdline-tools/latest/bin/sdkmanager", "cmdline-tools/bin/sdkmanager", "tools/bin/sdkmanager"]:
            p = candidate / sub
            if p.is_file():
                return str(p)
    return None
