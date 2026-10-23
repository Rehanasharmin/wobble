"""
Wobble Unified Dependency Manager
Coordinates Termux system packages (pkg/apt), Android SDK, JDK, Node (npm/yarn/pnpm),
Python (pip), and PHP (composer) dependencies with safety checks.
"""

import os
from pathlib import Path
from typing import Dict, Any, List, Optional

from wobble.core import packages
from wobble.core.context import find_tool, is_termux
from wobble.core.logger import get_logger
from wobble.core.executor import run_command, stream_command_result
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


def _privileged(cmd: List[str]) -> List[str]:
    """Prefix *cmd* with sudo on Linux hosts where the user is not root.

    Termux needs no escalation (pkg writes inside the app sandbox); Debian,
    Fedora and Arch refuse to install packages without it.
    """
    family = packages.package_family()
    if family in (packages.APT, packages.DNF, packages.PACMAN):
        try:
            is_root = os.geteuid() == 0
        except AttributeError:
            is_root = False
        if not is_root and find_tool("sudo"):
            return ["sudo"] + cmd
    return cmd


def _get_system_install_cmd(package_names: List[str]) -> List[str]:
    """Resolve the system install command for the detected package family.

    The family comes from :mod:`wobble.core.packages`, the same place the
    package *names* come from, so a Termux host can never be handed Debian
    package names (or vice versa) just because a binary happens to be on PATH.
    """
    family = packages.package_family()
    if family == packages.TERMUX:
        return ["pkg", "install", "-y"] + package_names
    if family == packages.APT:
        return _privileged(["apt-get", "install", "-y"] + package_names)
    if family == packages.DNF:
        return _privileged(["dnf", "install", "-y"] + package_names)
    if family == packages.PACMAN:
        return _privileged(["pacman", "-S", "--needed", "--noconfirm"] + package_names)
    # Unknown host: fall back to whichever manager exists.
    for tool, cmd in (("pkg", ["pkg", "install", "-y"]),
                      ("apt-get", ["apt-get", "install", "-y"]),
                      ("apt", ["apt", "install", "-y"]),
                      ("dnf", ["dnf", "install", "-y"]),
                      ("pacman", ["pacman", "-S", "--needed", "--noconfirm"])):
        if find_tool(tool):
            return _privileged(cmd + package_names)
    return ["pkg", "install", "-y"] + package_names


def _get_system_uninstall_cmd(package_name: str) -> List[str]:
    """Resolve the system uninstall command for the detected package family."""
    family = packages.package_family()
    if family == packages.TERMUX:
        return ["pkg", "uninstall", "-y", package_name]
    if family == packages.APT:
        return _privileged(["apt-get", "remove", "-y", package_name])
    if family == packages.DNF:
        return _privileged(["dnf", "remove", "-y", package_name])
    if family == packages.PACMAN:
        return _privileged(["pacman", "-R", "--noconfirm", package_name])
    for tool, cmd in (("pkg", ["pkg", "uninstall", "-y"]),
                      ("apt-get", ["apt-get", "remove", "-y"]),
                      ("apt", ["apt", "remove", "-y"]),
                      ("dnf", ["dnf", "remove", "-y"]),
                      ("pacman", ["pacman", "-R", "--noconfirm"])):
        if find_tool(tool):
            return _privileged(cmd + [package_name])
    return ["pkg", "uninstall", "-y", package_name]


def _run_dependency_command(cmd: List[str], cwd: Optional[Path] = None, **fields: Any) -> Dict[str, Any]:
    """Run a package manager without mixing child output into JSON responses."""
    logger = get_logger()
    result = stream_command_result(
        cmd, cwd=cwd, capture_output=logger.json_mode
    )
    data = result.to_dict()
    data.update(fields)
    data["exit_code"] = result.returncode
    return data


def _install_android_sdk(logger) -> Dict[str, Any]:
    """Install Android SDK components with sdkmanager.

    No Linux distribution and no Termux package ships a usable Android SDK, so
    "wob deps install android-sdk" must drive Google's sdkmanager instead of
    pretending apt/pkg can provide it.
    """
    from wobble.android.sdk import find_sdkmanager

    sdkmanager = find_sdkmanager()
    if not sdkmanager:
        return {
            "success": False,
            "target": "android-sdk",
            "error": "sdkmanager was not found, and the Android SDK is not installable "
                     "from Termux's or your distribution's package repository.",
            "error_code": "sdkmanager_not_found",
            "hint": packages.android_sdk_hint(),
        }

    logger.heading("Android SDK")
    wanted = list(packages.ANDROID_SDK_PACKAGES)
    logger.step(f"sdkmanager packages to install: {', '.join(wanted)}")
    result = run_command([sdkmanager, *wanted], timeout=None)
    data = result.to_dict()
    data.update({"target": "android-sdk", "installed": wanted,
                 "exit_code": result.returncode})
    if not result.success:
        data["success"] = False
        data["error"] = ("sdkmanager failed. Licences may need accepting first: "
                         "run 'yes | sdkmanager --licenses'.")
        data["error_code"] = "sdkmanager_failed"
    return data


def deps_install(target: Optional[str] = None, project_dir: Optional[Path] = None) -> Dict[str, Any]:
    """
    Install project dependencies or a predefined toolchain stack.
    Targets: 'android-toolchain', 'node', 'python', 'php', or empty for current project.
    """
    logger = get_logger()
    cwd = (project_dir or Path.cwd()).resolve()

    # Predefined toolchain stacks
    if target in ("android", "android-toolchain"):
        logger.heading("Android toolchain")
        # Names come from wobble.core.packages, which mirrors the real Termux
        # repositories: aapt ships zipalign, aapt2 is a split package, and
        # apksigner is separate.  openjdk-17 is the JDK the AGP targets.
        keys = ["jdk", "gradle", "aapt", "aapt2", "apksigner", "zip"]
        pkgs = packages.packages_for(keys)
        command = packages.install_command(keys)
        if not command:
            return {
                "success": False,
                "target": target,
                "error": "No supported package manager was found.",
                "error_code": "package_manager_unavailable",
                "hint": "Install Termux's pkg (F-Droid/GitHub build) or a host "
                        "package manager such as apt, dnf or pacman.",
            }
        unavailable = packages.unsupported_keys(keys)
        logger.step(f"System packages to install: {', '.join(pkgs)}")
        argv = _get_system_install_cmd(pkgs)
        result = _run_dependency_command(argv, target=target, installed=pkgs,
                                         command_line=" ".join(argv))
        if unavailable:
            result["unavailable"] = unavailable
            result["note"] = (
                "Google's Android build-tools (aapt2, apksigner, zipalign) are not "
                "packaged outside Termux; use 'wob deps install android-sdk' with "
                "sdkmanager on your distribution."
            )
        return result

    if target == "android-sdk":
        return _install_android_sdk(logger)

    if target in ("node", "nodejs", "web"):
        logger.heading("Node.js")
        cmd = _get_system_install_cmd(packages.packages_for(["nodejs"]))
        return _run_dependency_command(cmd, target=target)

    if target in ("python", "python3"):
        logger.heading("Python")
        # Debian/Fedora call this "python3", Termux calls it "python"; the map
        # resolves both instead of installing a non-existent "python" package.
        cmd = _get_system_install_cmd(packages.packages_for(["python"]))
        return _run_dependency_command(cmd, target=target)

    if target in ("php",):
        logger.heading("PHP")
        cmd = _get_system_install_cmd(packages.packages_for(["php"]))
        return _run_dependency_command(cmd, target=target)

    if target:
        return {
            "success": False,
            "error": f"Unknown dependency stack '{target}'.",
            "error_code": "unknown_dependency_stack",
            "hint": "Use android, android-sdk, node, python, or php; omit the stack "
                    "for the current project.",
        }

    # Project-level dependencies
    spec = find_current_project(cwd)
    pkg_mgr = resolve_package_manager(cwd, "auto")

    logger.heading(f"Dependencies ({pkg_mgr})")

    if pkg_mgr in ("npm", "pnpm", "yarn"):
        tool_bin = find_tool(pkg_mgr)
        if not tool_bin:
            return {"success": False,
                    "error": f"{pkg_mgr} not found. "
                             f"{packages.install_hint(('nodejs',), 'Install Node.js with: ')}"}
        return _run_dependency_command([tool_bin, "install"], cwd=cwd, manager=pkg_mgr)

    elif pkg_mgr == "pip":
        py_bin = find_tool("python3") or find_tool("python")
        if not py_bin:
            return {"success": False,
                    "error": "Python not found. "
                             + (packages.install_hint(("python",), "Run ") or "")}
        req_file = cwd / "requirements.txt"
        if req_file.exists():
            return _run_dependency_command(
                [py_bin, "-m", "pip", "install", "-r", "requirements.txt"],
                cwd=cwd, manager="pip",
            )
        return {"success": True, "notice": "No requirements.txt file found"}

    elif pkg_mgr == "composer":
        comp_bin = find_tool("composer")
        if not comp_bin:
            return {"success": False, "error": "Composer not found."}
        return _run_dependency_command([comp_bin, "install"], cwd=cwd, manager="composer")

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

    return _run_dependency_command(
        cmd, cwd=cwd, package=package_name, manager=resolved_mgr
    )


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

    return _run_dependency_command(
        cmd, cwd=cwd, package=package_name, manager=resolved_mgr
    )


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
                "fix": packages.install_hint(("python",), "Run ")
            })

    if (cwd / "app" / "build.gradle").exists():
        java_bin = find_tool("java")
        if not java_bin:
            report["issues"].append({
                "type": "missing_java",
                "message": "Java JDK is missing.",
                "fix": packages.install_hint(("jdk",), "Run ")
            })

    report["status"] = "ok" if len(report["issues"]) == 0 else "needs_attention"
    return report


def deps_list(project_dir: Optional[Path] = None) -> Dict[str, Any]:
    """List declared dependencies for current project."""
    import json
    cwd = (project_dir or Path.cwd()).resolve()
    spec = find_current_project(cwd)

    result: Dict[str, Any] = {
        "success": True,
        "project": spec.name if spec else cwd.name,
        "dependencies": {},
        "dev_dependencies": {},
        "system": [],
        "errors": [],
    }

    pkg_json = cwd / "package.json"
    if pkg_json.exists():
        try:
            with pkg_json.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, dict):
                raise ValueError("package.json root must be a JSON object")
            dependencies = data.get("dependencies", {})
            dev_dependencies = data.get("devDependencies", {})
            if not isinstance(dependencies, dict) or not isinstance(dev_dependencies, dict):
                raise ValueError("dependencies and devDependencies must be JSON objects")
            result["dependencies"] = dependencies
            result["dev_dependencies"] = dev_dependencies
        except (OSError, UnicodeError, ValueError, TypeError, AttributeError) as exc:
            result["errors"].append({"path": str(pkg_json), "error": str(exc)})

    req_txt = cwd / "requirements.txt"
    if req_txt.exists():
        try:
            with req_txt.open("r", encoding="utf-8") as handle:
                lines = []
                for raw_line in handle:
                    line = raw_line.strip()
                    if line and not line.startswith("#"):
                        lines.append(line)
                result["dependencies"]["pip"] = lines
        except (OSError, UnicodeError) as exc:
            result["errors"].append({"path": str(req_txt), "error": str(exc)})

    if spec and spec.dependencies:
        result["system"] = spec.dependencies.get("system", [])

    if result["errors"]:
        result["success"] = False
        result["error"] = "Some dependency files could not be read."
        result["error_code"] = "dependency_file_invalid"
        result["hint"] = "Fix the listed files, then run 'wob deps list' again."
    return result
