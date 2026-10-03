"""
Wobble Web Framework Detector
Identifies web frameworks automatically based on project files, configuration, and dependencies.
"""

from pathlib import Path
from typing import Optional

from wobble.plugins.loader import detect_plugin_for_path, list_plugins
from wobble.project.spec import ProjectSpec


def detect_web_framework(directory: Path) -> str:
    """Determine the web framework used in the target directory."""
    # 1. Check wobble.json spec if present
    spec = ProjectSpec.load_from_dir(directory)
    if spec and spec.framework and spec.framework != "unknown":
        return spec.framework

    # 2. Check plugin detection
    detected = detect_plugin_for_path(directory)
    if detected and detected.category == "web":
        return detected.name

    # 3. Check for static web indicators
    if (directory / "index.html").exists():
        return "static_web"

    return "generic_web"
