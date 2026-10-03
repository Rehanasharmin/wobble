"""
Wobble Unified Dependency Manager
Coordinates Termux system packages (pkg/apt), Android SDK, JDK, Node (npm/yarn/pnpm),
Python (pip), and PHP (composer) dependencies with safety checks.
"""

from pathlib import Path
from typing import Dict, Any, List, Optional

from wobble.core.context import find_tool, is_termux
from wobble.core.logger import get_logger
from wobble.core.executor import run_command, stream_command
from wobble.project.manager import find_current_project


def resolve_package_manager(project_path: Path, requested_manager: str = "auto") -> str:
    """Resolve the target package manager based on user preference or project detection."""
    if requested_manager != "auto":
        return requested_manager

    # Project context
    if (project_path / "package.json").exists():
        if (project_path / "pnpm-lock.yaml").exists() and find_tool("pnpm"):
            return "pnpm"
        if (project_path / "yarn.lock").exists() and find_tool("yarn"):
            return "yarn"
        return "npm"

    if (project_path / "requirements.txt").exists() or (project_path / "pyproject.toml").exists():
        return "pip"

    if (project_path / "composer.json").exists():
        return "composer"

    # Default to system Termux manager
    return "termux"


def _get_system_install_cmd(packages: List[str]) -> List[str]:
    """Resolve system install command based on available package manager."""
    if find_tool("pkg"):
        return ["pkg", "install", "-y"] + packages
    elif find_tool("apt-get"):
        return ["apt-get", "install", "-y"] + packages
    elif find_tool("apt"):
        return ["apt", "install", "-y"] + packages
    return ["pkg", "install", "-y"] + packages


def _get_system_uninstall_cmd(package_name: str) -> List[str]:
    """Resolve system uninstall command based on available package manager."""
    if find_tool("pkg"):
        return ["pkg", "uninstall", "-y", package_name]
    elif find_tool("apt-get"):
        return ["apt-get", "remove", "-y", package_name]
    elif find_tool("apt"):
        return ["apt", "remove", "-y", package_name]
    return ["pkg", "uninstall", "-y", package_name]


def deps_install(target: Optional[str] = None, project_dir: Optional[Path] = None) -> Dict[str, Any]:
    """
    Install project dependencies or a predefined toolchain stack.
    Targets: 'android-toolchain', 'node', 'python', 'php', or empty for current project.
    """
    logger = get_logger()
    cwd = (project_dir or Path.cwd()).resolve()

    # Predefined toolchain stacks
    if target in ("android", "android-sdk", "android-toolchain"):
        logger.heading("Installing Android Toolchain via System Package Manager")
        pkgs = ["openjdk-17", "aapt", "apksigner", "zip", "unzip"]
        logger.step(f"System packages to install: {', '.join(pkgs)}")
        cmd = _get_system_install_cmd(pkgs)
        exit_code = stream_command(cmd)
        return {"success": exit_code == 0, "target": target, "installed": pkgs}

    if target in ("node", "nodejs", "web"):
        logger.heading("Installing Node.js & Web Toolchain")
        cmd = _get_system_install_cmd(["nodejs"])
        exit_code = stream_command(cmd)
        return {"success": exit_code == 0, "target": target}

    if target in ("python", "python3"):
        logger.heading("Installing Python 3")
        cmd = _get_system_install_cmd(["python"])
        exit_code = stream_command(cmd)
        return {"success": exit_code == 0, "target": target}

    if target in ("php",):
        logger.heading("Installing PHP")
        cmd = _get_system_install_cmd(["php"])
        exit_code = stream_command(cmd)
        return {"success": exit_code == 0, "target": target}

    # Project-level dependencies
    spec = find_current_project(cwd)
    pkg_mgr = resolve_package_manager(cwd, "auto")

    logger.heading(f"Installing Project Dependencies using '{pkg_mgr}'")

    if pkg_mgr in ("npm", "pnpm", "yarn"):
        tool_bin = find_tool(pkg_mgr)
        if not tool_bin:
            return {"success": False, "error": f"{pkg_mgr} not found. Please install nodejs: pkg install -y nodejs"}
        exit_code = stream_command([tool_bin, "install"], cwd=cwd)
        return {"success": exit_code == 0, "manager": pkg_mgr}

    elif pkg_mgr == "pip":
        py_bin = find_tool("python3") or find_tool("python")
        if not py_bin:
            return {"success": False, "error": "Python not found. Run: pkg install -y python"}
        req_file = cwd / "requirements.txt"
        if req_file.exists():
            exit_code = stream_command([py_bin, "-m", "pip", "install", "-r", "requirements.txt"], cwd=cwd)
            return {"success": exit_code == 0, "manager": "pip"}
        return {"success": True, "notice": "No requirements.txt file found"}

    elif pkg_mgr == "composer":
        comp_bin = find_tool("composer")
        if not comp_bin:
            return {"success": False, "error": "Composer not found."}
        exit_code = stream_command([comp_bin, "install"], cwd=cwd)
        return {"success": exit_code == 0, "manager": "composer"}

    elif spec and spec.project_type == "android":
        logger.info("Android project: dependencies are managed by Gradle during build.")
        return {"success": True, "manager": "gradle"}

    return {"success": True, "notice": "No project dependency file recognized."}


def deps_add(package_name: str, manager: str = "auto", project_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Add a package via the designated package manager."""
    logger = get_logger()
    cwd = (project_dir or Path.cwd()).resolve()
    resolved_mgr = resolve_package_manager(cwd, manager)

    logger.info(f"Adding '{package_name}' via {resolved_mgr}...")

    if resolved_mgr == "termux":
        cmd = _get_system_install_cmd([package_name])
    elif resolved_mgr == "npm":
        cmd = ["npm", "install", package_name]
    elif resolved_mgr == "pnpm":
        cmd = ["pnpm", "add", package_name]
    elif resolved_mgr == "yarn":
        cmd = ["yarn", "add", package_name]
    elif resolved_mgr == "pip":
        py_bin = find_tool("python3") or "python"
        cmd = [py_bin, "-m", "pip", "install", package_name]
    elif resolved_mgr == "composer":
        cmd = ["composer", "require", package_name]
    else:
        return {"success": False, "error": f"Unknown package manager: {resolved_mgr}"}

    exit_code = stream_command(cmd, cwd=cwd)
    return {
        "success": exit_code == 0,
        "package": package_name,
        "manager": resolved_mgr,
        "command": " ".join(cmd)
    }


def deps_remove(package_name: str, manager: str = "auto", project_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Remove a dependency."""
    logger = get_logger()
    cwd = (project_dir or Path.cwd()).resolve()
    resolved_mgr = resolve_package_manager(cwd, manager)

    logger.info(f"Removing '{package_name}' via {resolved_mgr}...")

    if resolved_mgr == "termux":
        cmd = _get_system_uninstall_cmd(package_name)
    elif resolved_mgr in ("npm", "pnpm", "yarn"):
        cmd = [resolved_mgr, "remove", package_name]
    elif resolved_mgr == "pip":
        py_bin = find_tool("python3") or "python"
        cmd = [py_bin, "-m", "pip", "uninstall", "-y", package_name]
    elif resolved_mgr == "composer":
        cmd = ["composer", "remove", package_name]
    else:
        return {"success": False, "error": f"Unknown package manager: {resolved_mgr}"}

    exit_code = stream_command(cmd, cwd=cwd)
    return {
        "success": exit_code == 0,
        "package": package_name,
        "manager": resolved_mgr,
        "command": " ".join(cmd)
    }


def deps_doctor(project_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Inspect and report on dependencies for the current project."""
    cwd = (project_dir or Path.cwd()).resolve()
    spec = find_current_project(cwd)

    report = {
        "project": spec.name if spec else cwd.name,
        "type": spec.project_type if spec else "unknown",
        "framework": spec.framework if spec else "unknown",
        "issues": []
    }

    if (cwd / "package.json").exists():
        if not (cwd / "node_modules").is_dir():
            report["issues"].append({
                "type": "missing_node_modules",
                "message": "node_modules directory is missing.",
                "fix": "Run 'wob deps install' or 'npm install'"
            })

    if (cwd / "requirements.txt").exists():
        py_bin = find_tool("python3")
        if not py_bin:
            report["issues"].append({
                "type": "missing_python",
                "message": "Python 3 is not installed.",
                "fix": "Run 'pkg install -y python'"
            })

    if (cwd / "app" / "build.gradle").exists():
        java_bin = find_tool("java")
        if not java_bin:
            report["issues"].append({
                "type": "missing_java",
                "message": "Java JDK is missing.",
                "fix": "Run 'pkg install -y openjdk-17'"
            })

    report["status"] = "ok" if len(report["issues"]) == 0 else "needs_attention"
    return report


def deps_list(project_dir: Optional[Path] = None) -> Dict[str, Any]:
    """List declared dependencies for current project."""
    import json
    cwd = (project_dir or Path.cwd()).resolve()
    spec = find_current_project(cwd)

    result: Dict[str, Any] = {
        "project": spec.name if spec else cwd.name,
        "dependencies": {},
        "dev_dependencies": {},
        "system": []
    }

    pkg_json = cwd / "package.json"
    if pkg_json.exists():
        try:
            with open(pkg_json, "r", encoding="utf-8") as f:
                data = json.load(f)
                result["dependencies"] = data.get("dependencies", {})
                result["dev_dependencies"] = data.get("devDependencies", {})
        except Exception:
            pass

    req_txt = cwd / "requirements.txt"
    if req_txt.exists():
        try:
            with open(req_txt, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]
                result["dependencies"]["pip"] = lines
        except Exception:
            pass

    if spec and spec.dependencies:
        result["system"] = spec.dependencies.get("system", [])

    return result
