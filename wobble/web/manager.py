"""
Wobble Web Development Manager
Coordinates development servers, builds, test execution, preview, and static serving.
"""

from pathlib import Path
from typing import Dict, Any, Optional

from wobble.core.errors import PreviewError
from wobble.core.logger import get_logger
from wobble.core.executor import stream_command_result, run_command
from wobble.core.context import get_lan_ip
from wobble.plugins.loader import detect_plugin_for_path, get_plugin
from wobble.web.detector import detect_web_framework
from wobble.web.preview import start_static_preview, find_free_port


def run_web_dev(project_path: Path, port: Optional[int] = None, host: str = "127.0.0.1") -> int:
    """Launch framework development server or fallback to static preview."""
    logger = get_logger()
    fw = detect_web_framework(project_path)
    plugin = get_plugin(fw)

    target_port = port or 3000
    lan_ip = get_lan_ip()

    if plugin:
        cmd = plugin.get_dev_command(project_path, {"port": target_port, "host": host})
        if cmd:
            logger.heading(f"{plugin.name} dev server")
            logger.detail("local", f"http://localhost:{target_port}/")
            lan_exposed = host not in ("127.0.0.1", "localhost", "::1")
            if lan_exposed:
                if lan_ip and lan_ip != "127.0.0.1":
                    logger.detail("network", f"http://{lan_ip}:{target_port}/")
                logger.warn("exposed on your LAN; stop the server when you leave this network")
            else:
                logger.detail("lan", "off (use --lan to enable)")
            logger.step(f"running: {' '.join(cmd)}")
            # Framework scripts (notably the generated Flask app) read these.
            extra_env = {"PORT": str(target_port), "WOBBLE_HOST": host}
            result = stream_command_result(
                cmd, cwd=project_path, env=extra_env,
                capture_output=logger.json_mode,
            )
            if logger.json_mode:
                logger.json_output(result.to_dict())
            return result.returncode

    # Fallback to static preview
    logger.info(f"Framework '{fw}' has no dev server script. Launching Wobble web preview...")
    return start_static_preview(project_path, target_port, host)


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
    return res.to_dict()


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
    return res.to_dict()


def run_web_preview(project_path: Path, port: Optional[int] = None, target_sub_dir: Optional[str] = None,
                    host: str = "127.0.0.1") -> int:
    """
    Preview the project. Checks for build output folders (dist, build, out, public)
    or serves root directory.
    """
    serve_dir = project_path
    if target_sub_dir:
        candidate = (project_path / target_sub_dir).expanduser().resolve()
        if not candidate.is_dir():
            raise PreviewError(
                f"Requested preview directory is missing or not a directory: {candidate}",
                code="preview_directory_not_found",
                hint="Check --dir, or run 'wob web build' to generate the output directory.",
                details={"directory": str(candidate)},
            )
        serve_dir = candidate
    else:
        # Check standard build output directories
        for build_folder in ["dist", "build", "out", "public"]:
            candidate = project_path / build_folder
            try:
                populated = candidate.is_dir() and any(candidate.iterdir())
            except OSError:
                populated = False
            if populated:
                serve_dir = candidate
                break

    return start_static_preview(serve_dir, port, host)
