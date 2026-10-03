"""
Wobble Web Development Manager
Coordinates development servers, builds, test execution, preview, and static serving.
"""

from pathlib import Path
from typing import Dict, Any, Optional

from wobble.core.logger import get_logger
from wobble.core.executor import stream_command, run_command
from wobble.core.context import get_lan_ip
from wobble.plugins.loader import detect_plugin_for_path, get_plugin
from wobble.web.detector import detect_web_framework
from wobble.web.preview import start_static_preview, find_free_port


def run_web_dev(project_path: Path, port: Optional[int] = None, host: str = "0.0.0.0") -> int:
    """Launch framework development server or fallback to static preview."""
    logger = get_logger()
    fw = detect_web_framework(project_path)
    plugin = get_plugin(fw)

    target_port = port or 3000
    lan_ip = get_lan_ip()

    if plugin:
        cmd = plugin.get_dev_command(project_path, {"port": target_port, "host": host})
        if cmd:
            logger.heading(f"Starting {plugin.name} Dev Server")
            logger.detail("Local URL", f"http://localhost:{target_port}/")
            if lan_ip and lan_ip != "127.0.0.1":
                logger.detail("Network LAN URL", f"http://{lan_ip}:{target_port}/")
            logger.step(f"Running: {' '.join(cmd)}")
            return stream_command(cmd, cwd=project_path)

    # Fallback to static preview
    logger.info(f"Framework '{fw}' has no dev server script. Launching Wobble web preview...")
    start_static_preview(project_path, target_port, host)
    return 0


def run_web_build(project_path: Path) -> Dict[str, Any]:
    """Execute production build for the web application."""
    logger = get_logger()
    fw = detect_web_framework(project_path)
    plugin = get_plugin(fw)

    if not plugin:
        return {"success": False, "error": f"No plugin found for framework: {fw}"}

    cmd = plugin.get_build_command(project_path)
    if not cmd:
        logger.info(f"Framework '{fw}' does not require a build step (pure static).")
        return {"success": True, "notice": "Static project, no build compilation needed"}

    logger.step(f"Building web project ({' '.join(cmd)})...")
    res = run_command(cmd, cwd=project_path)
    return {
        "success": res.success,
        "returncode": res.returncode,
        "stdout": res.stdout,
        "stderr": res.stderr
    }


def run_web_test(project_path: Path) -> Dict[str, Any]:
    """Run tests for the web project."""
    fw = detect_web_framework(project_path)
    plugin = get_plugin(fw)

    if not plugin:
        return {"success": False, "error": "No plugin found for current project"}

    cmd = plugin.get_test_command(project_path)
    if not cmd:
        return {"success": True, "notice": "No test suite configured for this project"}

    res = run_command(cmd, cwd=project_path)
    return {
        "success": res.success,
        "stdout": res.stdout,
        "stderr": res.stderr
    }


def run_web_preview(project_path: Path, port: Optional[int] = None, target_sub_dir: Optional[str] = None):
    """
    Preview the project. Checks for build output folders (dist, build, out, public)
    or serves root directory.
    """
    serve_dir = project_path
    if target_sub_dir:
        candidate = project_path / target_sub_dir
        if candidate.is_dir():
            serve_dir = candidate
    else:
        # Check standard build output directories
        for build_folder in ["dist", "build", "out", "public"]:
            candidate = project_path / build_folder
            if candidate.is_dir() and any(candidate.iterdir()):
                serve_dir = candidate
                break

    start_static_preview(serve_dir, port)
