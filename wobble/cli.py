"""
Wobble Unified CLI Dispatcher
Entry point for all 'wob' subcommands, options, and structured JSON outputs.
"""

from __future__ import annotations

import sys
import os
import re
import argparse
from pathlib import Path

from wobble import __version__
from wobble.core.errors import (
    EXIT_FAILURE,
    EXIT_INTERRUPTED,
    RegistryError,
    UsageError,
    WobbleError,
    unexpected_error_payload,
)
from wobble.core.logger import Logger, set_logger, get_logger

# NOTE: heavyweight subcommand modules (doctor, apk, web, deps, plugins) are
# imported lazily inside their handlers. This keeps 'wob --version' and other
# trivial commands fast on mobile CPUs where import time is noticeable.


class WobbleArgumentParser(argparse.ArgumentParser):
    """Raise parse errors so ``main`` can honor JSON mode and return exit 2."""

    def error(self, message: str):
        raise UsageError(
            message,
            hint=f"Run '{self.prog} --help' for usage.",
            details={"usage": self.format_usage().strip()},
        )


def _port_number(value: str) -> int:
    """Argparse type for a real, bindable TCP port (zero is not meaningful here)."""
    try:
        port = int(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError("port must be an integer between 1 and 65535")
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port


def _add_target_args(parser: argparse.ArgumentParser) -> None:
    """Shared ``--root``/``--bin`` overrides for self-diagnostic subcommands."""
    parser.add_argument("--root", help="Installation root to inspect (default: detected)")
    parser.add_argument("--bin", help="Launcher directory to inspect (default: ~/.local/bin)")


def build_parser() -> argparse.ArgumentParser:
    """Construct the main argument parser for Wobble CLI."""
    parser = WobbleArgumentParser(
        prog="wob",
        description="Wobble - the Termux development harness for Android and web projects",
        epilog="""examples:
  wob doctor                        audit the environment and detect regressions
  wob doctor --only android --timings   focus on the SDK and show where time goes
  wob create android myapp          scaffold a native Android project
  wob create web site -f react      scaffold a React web project
  wob apk build && wob apk install  build and install a debug APK
  wob web preview --lan             preview on localhost and your Wi-Fi
  wob self status                   fast installation health report (--deep to hash)
  wob self repair                   fix launchers, bytecode, debris, corrupt config
  wob self watch                    watch for breakage live
  wob self incidents                read the recorded failure ledger
  wob --json project list           machine-readable output for scripts

Docs: README.md  |  Agent guide: AI_GUIDE.md  |  Schema: wob schema""",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument("--version", action="version", version=f"Wobble v{__version__}")
    parser.add_argument("--json", action="store_true", help="Format output as JSON for AI agents and scripts")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI color formatting")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose diagnostics")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # 1. wob create
    p_create = subparsers.add_parser("create", help="Create a new Android or Web project")
    p_create.add_argument("type", choices=["android", "web"], help="Project archetype")
    p_create.add_argument("name", help="Project name / directory")
    p_create.add_argument("-f", "--framework", default="auto", help="Framework template (e.g. vite, react, vue, svelte, nextjs, python, php, static)")
    p_create.add_argument("-p", "--package", help="Android package ID (e.g. com.example.myapp)")
    p_create.add_argument("-d", "--dir", help="Destination folder (defaults to current dir / name)")

    # 2. wob project
    p_project = subparsers.add_parser("project", help="Manage and inspect projects")
    sp_project = p_project.add_subparsers(dest="subcommand")
    p_proj_list = sp_project.add_parser("list", help="List registered & local projects")
    p_proj_list.add_argument("--path", help="Directory to scan")
    p_proj_info = sp_project.add_parser("info", help="Show project metadata and statistics")
    p_proj_info.add_argument("--path", help="Project root directory")
    p_proj_open = sp_project.add_parser("open", help="Inspect and display project quick-commands")
    p_proj_open.add_argument("name", help="Project name or directory")
    p_proj_rm = sp_project.add_parser("remove", help="Unregister a project from registry")
    p_proj_rm.add_argument("name", help="Project name to unregister")

    # 3. wob android
    p_android = subparsers.add_parser("android", help="Native Android development")
    sp_android = p_android.add_subparsers(dest="subcommand")
    p_and_build = sp_android.add_parser("build", help="Compile project into APK with Gradle")
    p_and_build.add_argument("--release", action="store_true", help="Build release APK")
    p_and_build.add_argument("--clean", action="store_true", help="Clean prior build before compiling")
    sp_android.add_parser("clean", help="Clean Gradle build files")
    sp_android.add_parser("info", help="Inspect Android project configuration")
    sp_android.add_parser("limitations", help="Report Termux & Android OS technical constraints honestly")

    # 4. wob web
    p_web = subparsers.add_parser("web", help="Web development workflows")
    sp_web = p_web.add_subparsers(dest="subcommand")
    p_web_dev = sp_web.add_parser("dev", help="Start framework development server")
    p_web_dev.add_argument("-p", "--port", type=_port_number, help="Port to listen on (1-65535)")
    p_web_dev.add_argument("--host", default=None, help="Host address to bind (default: 127.0.0.1)")
    p_web_dev.add_argument("--lan", action="store_true", help="Expose the dev server on your LAN (0.0.0.0)")
    sp_web.add_parser("build", help="Build web application for distribution")
    sp_web.add_parser("test", help="Run web test suite")
    p_web_prev = sp_web.add_parser("preview", help="Start the hardened preview server (localhost by default)")
    p_web_prev.add_argument("-p", "--port", type=_port_number, help="Port to serve on (1-65535)")
    p_web_prev.add_argument("--dir", help="Directory to serve")
    p_web_prev.add_argument("--host", default=None, help="Host address to bind (default: 127.0.0.1)")
    p_web_prev.add_argument("--lan", action="store_true", help="Expose the preview on your LAN (0.0.0.0)")
    p_web_serve = sp_web.add_parser("serve", help="Static HTTP file server")
    p_web_serve.add_argument("-p", "--port", type=_port_number, help="Port to serve on (1-65535)")
    p_web_serve.add_argument("--host", default=None, help="Host address to bind (default: 127.0.0.1)")
    p_web_serve.add_argument("--lan", action="store_true", help="Expose the server on your LAN (0.0.0.0)")

    # 5. wob apk
    p_apk = subparsers.add_parser("apk", help="Locate, inspect, build, and install APKs")
    sp_apk = p_apk.add_subparsers(dest="subcommand")
    p_apk_build = sp_apk.add_parser("build", help="Build APK for current project")
    p_apk_build.add_argument("--release", action="store_true", help="Build release APK")
    p_apk_list = sp_apk.add_parser("list", help="Find all generated APKs")
    p_apk_list.add_argument("--path", help="Directory to scan")
    p_apk_info = sp_apk.add_parser("info", help="Inspect APK details (package, SDK, size, permissions)")
    p_apk_info.add_argument("file", nargs="?", help="Path to APK file")
    p_apk_inst = sp_apk.add_parser("install", help="Safely install APK on Android (via termux-open, am, or adb)")
    p_apk_inst.add_argument("file", nargs="?", help="Path to APK file")
    p_apk_inst.add_argument("--method", choices=["auto", "termux-open", "am", "adb"], default="auto")
    p_apk_share = sp_apk.add_parser("share", help="Export APK to Android Downloads/shared folder")
    p_apk_share.add_argument("file", nargs="?", help="Path to APK file")
    p_apk_share.add_argument("--dest", help="Destination folder (defaults to ~/storage/shared/Download)")
    p_apk_sign = sp_apk.add_parser("sign", help="Sign APK using apksigner")
    p_apk_sign.add_argument("file", nargs="?", help="Path to APK file")
    p_apk_sign.add_argument("--keystore", help="Path to keystore file")
    p_apk_sign.add_argument("--alias", help="Key alias")
    sp_apk.add_parser("clean", help="Remove generated APKs")

    # 6. wob deps
    p_deps = subparsers.add_parser("deps", help="Unified package and dependency management")
    sp_deps = p_deps.add_subparsers(dest="subcommand")
    p_deps_inst = sp_deps.add_parser("install", help="Install dependencies for project or stack")
    p_deps_inst.add_argument("target", nargs="?", help="Stack name: android, node, python, php, or empty for current project")
    p_deps_add = sp_deps.add_parser("add", help="Add a dependency")
    p_deps_add.add_argument("package", help="Package name to add")
    p_deps_add.add_argument("-m", "--manager", choices=["auto", "termux", "npm", "pip", "composer"], default="auto")
    p_deps_rm = sp_deps.add_parser("remove", help="Remove a dependency")
    p_deps_rm.add_argument("package", help="Package name to remove")
    p_deps_rm.add_argument("-m", "--manager", choices=["auto", "termux", "npm", "pip", "composer"], default="auto")
    sp_deps.add_parser("doctor", help="Check dependencies health for project")
    sp_deps.add_parser("list", help="List project dependencies")

    # 7. wob doctor
    p_doctor = subparsers.add_parser(
        "doctor", help="Run comprehensive, cached environment health diagnostics")
    p_doctor.add_argument("--quick", action="store_true",
                          help="Skip subprocess version probes (PATH lookups only)")
    p_doctor.add_argument("--only", metavar="CATEGORIES",
                          help="Limit to categories: system, resources, environment, "
                               "tools, web, android, wobble (comma-separated)")
    p_doctor.add_argument("--strict", action="store_true",
                          help="Exit 1 when any check warns or fails (CI-friendly)")
    p_doctor.add_argument("--fail-on", choices=["never", "warning", "missing", "error"],
                          default="never", metavar="LEVEL",
                          help="Exit 1 at or above this severity (never|warning|missing|error)")
    p_doctor.add_argument("--timings", action="store_true",
                          help="Show per-section timing and probe-cache statistics")
    p_doctor.add_argument("--no-cache", action="store_true",
                          help="Ignore and do not write the probe cache")
    p_doctor.add_argument("--save-baseline", action="store_true",
                          help="Store this run as the regression baseline")
    p_doctor.add_argument("--no-save", action="store_true",
                          help="Do not update the regression baseline")

    # 8. wob plugin
    p_plugin = subparsers.add_parser("plugin", help="List and inspect framework plugins")
    sp_plugin = p_plugin.add_subparsers(dest="subcommand")
    sp_plugin.add_parser("list", help="List all available plugins")
    p_plug_info = sp_plugin.add_parser("info", help="Display details for a specific plugin")
    p_plug_info.add_argument("name", help="Plugin name")

    # 9. wob config
    p_config = subparsers.add_parser("config", help="Manage persistent user configuration")
    sp_config = p_config.add_subparsers(dest="subcommand")
    sp_config.add_parser("list", help="List all configuration values")
    p_cfg_get = sp_config.add_parser("get", help="Get a configuration setting")
    p_cfg_get.add_argument("key", help="Setting key")
    p_cfg_set = sp_config.add_parser("set", help="Update a configuration setting")
    p_cfg_set.add_argument("key", help="Setting key")
    p_cfg_set.add_argument("value", help="New value")

    # 10. wob clean
    p_clean = subparsers.add_parser("clean", help="Clean temporary caches and build files")
    p_clean.add_argument("--all", action="store_true", help="Deep clean including node_modules and Gradle cache")
    p_clean.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompt for destructive cleaning")

    # 11. wob self (install/verify/repair the application itself)
    p_self = subparsers.add_parser(
        "self", help="Inspect, repair, verify, or uninstall Wobble itself")
    sp_self = p_self.add_subparsers(dest="subcommand")

    for name, help_text in (
        ("status", "Fast health report: runtime, launcher, PATH, config, history"),
        ("health", "Alias for 'self status'"),
    ):
        p_self_status = sp_self.add_parser(name, help=help_text)
        p_self_status.add_argument("--deep", action="store_true",
                                   help="Hash every installed file and smoke-test imports")
        p_self_status.add_argument("--strict", action="store_true",
                                   help="Exit 1 on warnings as well as critical problems")
        p_self_status.add_argument("--brief", action="store_true",
                                   help="Print a single-line health summary")
        _add_target_args(p_self_status)

    p_self_verify = sp_self.add_parser(
        "verify", help="Verify installed files against the manifest (parallel SHA-256)")
    p_self_verify.add_argument("--serial", action="store_true",
                               help="Hash sequentially (debugging)")
    p_self_verify.add_argument("--strict", action="store_true",
                               help="Also fail when the launcher is not executable")
    _add_target_args(p_self_verify)

    p_self_repair = sp_self.add_parser(
        "repair", help="Fix launchers, bytecode, completions, debris, corrupt config")
    p_self_repair.add_argument("--compile", dest="compile", action="store_true", default=True,
                               help="Recompile missing bytecode (default)")
    p_self_repair.add_argument("--no-compile", dest="compile", action="store_false",
                               help="Skip bytecode compilation")
    p_self_repair.add_argument("--completions", dest="completions", action="store_true",
                               default=True, help="Regenerate shell completions (default)")
    p_self_repair.add_argument("--no-completions", dest="completions", action="store_false",
                               help="Skip shell completions")
    p_self_repair.add_argument("--config", dest="fix_config", action="store_true",
                               default=True, help="Back up corrupt config/registry (default)")
    p_self_repair.add_argument("--no-config", dest="fix_config", action="store_false",
                               help="Leave config/registry files alone")
    p_self_repair.add_argument("--path", action="store_true",
                               help="Add the launcher directory to shell startup files")
    p_self_repair.add_argument("--accept-current", action="store_true",
                               help="Re-baseline manifest hashes after a deliberate local patch")
    p_self_repair.add_argument("-y", "--yes", action="store_true",
                               help="Do not ask for confirmation with --accept-current")
    _add_target_args(p_self_repair)

    p_self_watch = sp_self.add_parser(
        "watch", help="Continuously watch installation health and report changes")
    p_self_watch.add_argument("--interval", type=float, default=2.0, metavar="SECONDS",
                              help="Seconds between checks (default 2, minimum 0.2)")
    p_self_watch.add_argument("--count", type=int, default=0, metavar="N",
                              help="Stop after N checks (default: run until Ctrl+C)")
    p_self_watch.add_argument("--deep", action="store_true",
                              help="Hash files on every tick (slow)")
    _add_target_args(p_self_watch)

    p_self_incidents = sp_self.add_parser(
        "incidents", help="Show or clear the recorded failure ledger")
    p_self_incidents.add_argument("--limit", type=int, default=10, metavar="N",
                                  help="Show at most N incidents (default 10)")
    p_self_incidents.add_argument("--clear", action="store_true",
                                  help="Delete the ledger after showing it")

    p_self_install = sp_self.add_parser("install", help="Install a standalone copy of Wobble")
    _add_install_args(p_self_install)
    p_self_uninstall = sp_self.add_parser("uninstall", help="Remove the Wobble installation")
    _add_uninstall_args(p_self_uninstall)

    # top-level aliases for discoverability
    p_install = subparsers.add_parser("install", help="Install Wobble as standalone software")
    _add_install_args(p_install)
    p_uninstall = subparsers.add_parser("uninstall", help="Remove Wobble from this system")
    _add_uninstall_args(p_uninstall)

    # 11b. wob update / version / help
    subparsers.add_parser("update", help="Check for Wobble updates")
    subparsers.add_parser("version", help="Print the Wobble version")
    subparsers.add_parser("help", help="Show this help message")

    # 11c. identity
    subparsers.add_parser("banner", help="Print the Wobble ASCII wordmark")
    subparsers.add_parser("about", help="Show version, install mode, and environment")

    # 12. wob schema
    subparsers.add_parser("schema", help="Output machine-readable CLI schema for AI agents")

    # 13. wob completion
    p_compl = subparsers.add_parser("completion", help="Generate shell completion script (bash or zsh)")
    p_compl.add_argument("shell", nargs="?", default="bash", choices=["bash", "zsh"], help="Shell to generate a script for")

    # Shortcuts
    p_build = subparsers.add_parser("build", help="Intelligent build for current project")
    p_build.add_argument("--release", action="store_true", help="Build release APK or production bundle")

    p_dev = subparsers.add_parser("dev", help="Start dev server for current project")
    p_dev.add_argument("-p", "--port", type=_port_number, help="Port to listen on (1-65535)")
    p_dev.add_argument("--host", default=None, help="Host address to bind (default: 127.0.0.1)")
    p_dev.add_argument("--lan", action="store_true", help="Expose on LAN (0.0.0.0)")

    p_prev = subparsers.add_parser("preview", help="Preview the current project locally (--lan for Wi-Fi)")
    p_prev.add_argument("-p", "--port", type=_port_number, help="Port to listen on (1-65535)")
    p_prev.add_argument("--host", default=None, help="Host address to bind (default: 127.0.0.1)")
    p_prev.add_argument("--lan", action="store_true", help="Expose on LAN (0.0.0.0)")

    return parser


def _add_install_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", help="Install directory (default: ~/.local/share/wobble)")
    parser.add_argument("--bin", help="Directory for the 'wob' launcher (default: ~/.local/bin)")
    parser.add_argument("--force", action="store_true", help="Replace an existing foreign 'wob' executable")
    parser.add_argument("--no-completion", action="store_true", help="Do not install shell completions")
    parser.add_argument("--no-path", action="store_true", help="Do not edit ~/.bashrc / ~/.zshrc")


def _add_uninstall_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", help="Install directory (default: ~/.local/share/wobble)")
    parser.add_argument("--purge", action="store_true", help="Also remove ~/.wobble config, cache and registry")
    parser.add_argument("-y", "--yes", action="store_true", help="Skip the confirmation prompt")


def _suggest_names(unknown: str, candidates) -> str:
    """Return a friendly 'Did you mean ...?' hint for mistyped names."""
    # Deferred import: difflib costs several milliseconds to import and is only
    # ever needed on the error path.
    import difflib
    matches = difflib.get_close_matches(unknown, list(candidates), n=3, cutoff=0.5)
    if matches:
        return f" Did you mean: {', '.join(matches)}?"
    return ""


_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_PACKAGE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+$")


def _validate_project_name(name: str) -> str:
    """
    Reject names that could escape the target directory, break generated
    Gradle/XML/JSON templates, or start a CLI flag.
    """
    if not name or name in (".", ".."):
        raise ValueError("Project name cannot be empty, '.' or '..'.")
    if not _NAME_RE.match(name):
        raise ValueError(
            "Project names may only contain letters, digits, dots, dashes and "
            "underscores (max 64 chars, must start with a letter or digit)."
        )
    return name


def handle_create(args) -> int:
    from wobble.plugins.loader import get_plugin, list_plugins
    from wobble.project.manager import register_project

    logger = get_logger()
    p_type = args.type
    name = args.name

    # Guard against names that would escape the target directory, break the
    # generated Gradle/XML/JSON templates, or be interpreted as a CLI flag.
    try:
        name = _validate_project_name(name)
    except ValueError as e:
        logger.error(f"Invalid project name '{name}'. {e}")
        return 1

    if args.package and not _PACKAGE_RE.match(args.package):
        logger.error(
            f"Invalid Android package ID '{args.package}'. "
            "Use reverse-DNS identifiers such as com.example.myapp."
        )
        return 1

    target_dir = Path(args.dir).expanduser() if args.dir else (Path.cwd() / name)

    if target_dir.is_symlink():
        logger.error(f"Refusing to scaffold into symlink '{target_dir}'.")
        return 1
    if target_dir.exists():
        try:
            non_empty = any(target_dir.iterdir())
        except OSError as e:
            logger.error(f"Cannot inspect target directory '{target_dir}': {e}")
            return 1
        if non_empty:
            logger.error(f"Target directory '{target_dir}' already exists and is not empty.")
            return 1

    framework = args.framework
    if framework == "auto":
        framework = "android" if p_type == "android" else "vite"

    plugin = get_plugin(framework)
    if not plugin:
        if p_type == "web" and framework in ("static", "static_web", "html"):
            plugin = get_plugin("static_web")
        elif p_type == "android":
            plugin = get_plugin("android")

    if not plugin:
        available = [p.name for p in list_plugins()]
        logger.error(
            f"No plugin found for framework '{framework}'. "
            f"Run 'wob plugin list' to see available frameworks.{_suggest_names(framework, available)}"
        )
        return 1

    logger.heading(f"Creating new {p_type.capitalize()} project: {name}")
    logger.detail("Framework", plugin.name)
    logger.detail("Location", str(target_dir))

    options = {
        "package": args.package or f"com.example.{name.lower().replace('-', '_')}",
        "app_name": name
    }

    success = plugin.create_project(name, target_dir, options)
    if success:
        registry_warning = None
        try:
            register_project(name, target_dir)
        except RegistryError as exc:
            # Scaffolding already succeeded; do not misreport it as a total
            # failure merely because the optional convenience registry is full
            # or read-only. Surface the degraded state explicitly instead.
            registry_warning = str(exc)
            logger.warn(f"Project was created, but could not be registered: {exc}")

        if logger.json_mode:
            result = {
                "success": True,
                "project": {
                    "name": name,
                    "path": str(target_dir.resolve()),
                    "type": p_type,
                    "framework": plugin.name,
                },
                "registered": registry_warning is None,
            }
            logger.json_output(result)
        else:
            logger.success(f"Project '{name}' successfully created!")
            print("\nNext steps:")
            print(f"  cd {target_dir}")
            if p_type == "android":
                print("  wob apk build       # Build debug APK")
                print("  wob apk install     # Install APK on phone")
            else:
                print("  wob deps install    # Install dependencies")
                print("  wob web dev         # Start development server")
                print("  wob web preview     # Preview locally (add --lan for Wi-Fi)")
            print()
        return 0
    else:
        logger.error("Project creation failed.")
        return 1


def handle_project(args) -> int:
    from wobble.project.manager import (
        find_current_project,
        list_projects,
        get_project_info,
        unregister_project
    )

    logger = get_logger()
    sub = args.subcommand or "list"

    if sub == "list":
        scan_dir = Path(args.path) if hasattr(args, "path") and args.path else Path.cwd()
        projects = list_projects(scan_dir)
        if logger.json_mode:
            logger.json_output({"projects": projects, "count": len(projects)})
        else:
            logger.heading("Detected & Registered Projects")
            if not projects:
                print("  No projects found. Create one with 'wob create android <name>' or 'wob create web <name>'")
            else:
                from wobble.core import theme
                for p in projects:
                    reg_tag = theme.paint("[registered]", theme.DIM, enabled=logger.use_color) if p["registered"] else ""
                    name = theme.paint(f"{p['name']:<18}", theme.BOLD, enabled=logger.use_color)
                    arrow = theme.paint("->", theme.CYAN, enabled=logger.use_color)
                    print(f"  {arrow} {name} ({p['type']} / {p['framework']}) - {p['path']} {reg_tag}")
            print()
        return 0

    elif sub == "info":
        target = Path(args.path) if hasattr(args, "path") and args.path else Path.cwd()
        info = get_project_info(target)
        if not info:
            logger.error("No Wobble project found in the current directory or specified path.")
            return 1
        if logger.json_mode:
            logger.json_output(info)
        else:
            logger.heading(f"Project Info: {info['name']}")
            logger.detail("Type", info.get("type"))
            logger.detail("Framework", info.get("framework"))
            logger.detail("Version", info.get("version"))
            if info.get("package_id"):
                logger.detail("Package ID", info.get("package_id"))
            logger.detail("Location", str(target.resolve()))
            metrics = info.get("metrics", {})
            logger.detail("Files", f"{metrics.get('file_count', 0)} files ({metrics.get('total_size_human', '')})")
            print()
        return 0

    elif sub == "open":
        name = args.name
        projs = list_projects()
        matched = [p for p in projs if p["name"] == name or p["path"] == name or name in p["path"]]
        if not matched:
            logger.error(f"Project '{name}' not found. Run 'wob project list' to view available projects.")
            return 1
        p = matched[0]
        if logger.json_mode:
            logger.json_output(p)
        else:
            logger.heading(f"Project: {p['name']}")
            print(f"  Path: {p['path']}")
            print(f"  Type: {p['type']} ({p['framework']})")
            print("\nQuick Commands:")
            print(f"  cd {p['path']}")
            if p["type"] == "android":
                print("  wob apk build")
                print("  wob apk install")
            else:
                print("  wob web dev")
                print("  wob web preview")
            print()
        return 0

    elif sub in ("remove", "unregister"):
        name = args.name
        if not unregister_project(name):
            logger.error(f"Project '{name}' is not registered. Run 'wob project list' to inspect the registry.")
            return 1
        if logger.json_mode:
            logger.json_output({"status": "unregistered", "project": name})
        else:
            logger.success(f"Project '{name}' removed from Wobble registry.")
        return 0
    return 0


def handle_android(args) -> int:
    import time as _time
    from wobble.project.manager import find_current_project
    from wobble.android.manager import build_android, clean_android
    from wobble.android.apk import find_apks
    from wobble.android.limitations import get_android_limitations_report

    logger = get_logger()
    sub = args.subcommand or "info"
    cwd = Path.cwd()

    if sub == "build":
        started = _time.monotonic()
        res = build_android(cwd, release=args.release, clean=args.clean)
        res["elapsed_seconds"] = round(_time.monotonic() - started, 1)
        if logger.json_mode:
            logger.json_output(res)
        elif res.get("success"):
            logger.detail("Build time", f"{res['elapsed_seconds']}s")
        return 0 if res.get("success") else 1

    elif sub == "clean":
        res = clean_android(cwd)
        if logger.json_mode:
            logger.json_output(res)
        else:
            if res.get("success"):
                logger.success("Android build directory cleaned.")
            else:
                logger.error(f"Clean failed: {res.get('stderr')}")
        return 0 if res.get("success") else 1

    elif sub == "info":
        spec = find_current_project(cwd)
        apks = find_apks(cwd)
        data = {
            "project": spec.to_dict() if spec else None,
            "generated_apks": [str(a) for a in apks]
        }
        if logger.json_mode:
            logger.json_output(data)
        else:
            logger.heading("Android Project Overview")
            if spec:
                logger.detail("Name", spec.name)
                logger.detail("Package ID", spec.package_id)
            logger.detail("APKs found", len(apks))
            for a in apks:
                logger.detail("  APK", a.name)
            print()
        return 0

    elif sub == "limitations":
        report = get_android_limitations_report()
        if logger.json_mode:
            logger.json_output(report)
        else:
            logger.heading(report["title"])
            print(f"  Philosophy: {report['philosophy']}\n")
            from wobble.core import theme
            for lim in report["limitations"]:
                topic = theme.paint(f"* {lim['topic']}", theme.BOLD, enabled=logger.use_color)
                print(f"  {topic}")
                print(f"    Reality:  {lim['reality']}")
                print(f"    Solution: {lim['solution']}")
                print()
        return 0
    return 0


def _resolve_host(args) -> str:
    """
    Localhost by default; LAN exposure is explicit.

    A dev server that serves raw project sources should never be reachable from
    the coffee-shop Wi-Fi unless the user asked for it with --lan/--host.
    """
    explicit = getattr(args, "host", None)
    if explicit:
        return explicit
    return "0.0.0.0" if getattr(args, "lan", False) else "127.0.0.1"


def handle_web(args) -> int:
    import time as _time
    from wobble.web.manager import run_web_dev, run_web_build, run_web_test, run_web_preview

    sub = args.subcommand or "preview"
    cwd = Path.cwd()
    host = _resolve_host(args)

    if sub == "dev":
        return run_web_dev(cwd, port=args.port, host=host)
    elif sub == "build":
        started = _time.monotonic()
        res = run_web_build(cwd)
        res["elapsed_seconds"] = round(_time.monotonic() - started, 1)
        if get_logger().json_mode:
            get_logger().json_output(res)
        elif res.get("success"):
            get_logger().detail("Build time", f"{res['elapsed_seconds']}s")
        else:
            get_logger().error(res.get("error") or res.get("stderr") or "Web build failed.")
        return 0 if res.get("success") else 1
    elif sub == "test":
        res = run_web_test(cwd)
        if get_logger().json_mode:
            get_logger().json_output(res)
        elif not res.get("success"):
            get_logger().error(res.get("error") or res.get("stderr") or "Web tests failed.")
        return 0 if res.get("success") else 1
    elif sub == "preview":
        return run_web_preview(cwd, port=args.port, target_sub_dir=args.dir, host=host)
    elif sub == "serve":
        return run_web_preview(cwd, port=args.port, host=host)
    return 0


def handle_apk(args) -> int:
    import time as _time
    from wobble.android.manager import build_android
    from wobble.android.apk import find_apks, inspect_apk, install_apk, share_apk, sign_apk

    logger = get_logger()
    sub = args.subcommand or "list"
    cwd = Path.cwd()

    if sub == "build":
        started = _time.monotonic()
        res = build_android(cwd, release=args.release)
        res["elapsed_seconds"] = round(_time.monotonic() - started, 1)
        if logger.json_mode:
            logger.json_output(res)
        elif res.get("success"):
            logger.detail("Build time", f"{res['elapsed_seconds']}s")
        return 0 if res.get("success") else 1

    elif sub == "list":
        scan_dir = Path(args.path) if hasattr(args, "path") and args.path else cwd
        apks = find_apks(scan_dir)
        if logger.json_mode:
            logger.json_output({"apks": [str(a) for a in apks], "count": len(apks)})
        else:
            logger.heading("Discovered APKs")
            if not apks:
                print("  No APKs found. Run 'wob apk build' to build one.")
            else:
                from wobble.core import theme
                for a in apks:
                    size = f"{round(a.stat().st_size / (1024 * 1024), 2)} MB"
                    name = theme.paint(a.name, theme.BOLD, enabled=logger.use_color)
                    arrow = theme.paint("->", theme.CYAN, enabled=logger.use_color)
                    print(f"  {arrow} {name} ({size}) - {a}")
            print()
        return 0

    elif sub == "info":
        target_apk = Path(args.file) if args.file else None
        if not target_apk:
            found = find_apks(cwd)
            if found:
                target_apk = found[0]
            else:
                logger.error("No APK specified and none found in project.")
                return 1

        info = inspect_apk(target_apk)
        if logger.json_mode:
            logger.json_output(info)
            return 0 if info.get("success") else 1
        if not info.get("success"):
            logger.error(info.get("error", "APK inspection failed."))
            if info.get("hint"):
                logger.hint(info["hint"])
            return 1
        else:
            logger.heading(f"APK Information: {info.get('file_name')}")
            logger.detail("Package Name", info.get("package_name"))
            logger.detail("App Label", info.get("app_label"))
            logger.detail("Version", f"{info.get('version_name')} (Code: {info.get('version_code')})")
            logger.detail("SDK Support", f"Min: {info.get('min_sdk')} | Target: {info.get('target_sdk')}")
            logger.detail("File Size", info.get("size_human"))
            logger.detail("SHA-256", info.get("sha256"))
            logger.detail("Native ABIs", ", ".join(info.get("native_abis", [])))
            perms = info.get("permissions", [])
            if perms:
                logger.detail("Permissions", f"{len(perms)} declared ({', '.join(perms[:3])}...)")
            print()
        return 0

    elif sub == "install":
        target_apk = Path(args.file) if args.file else None
        if not target_apk:
            found = find_apks(cwd)
            if found:
                target_apk = found[0]
            else:
                logger.error("No APK specified and none found in project.")
                return 1

        res = install_apk(target_apk, method=args.method)
        if logger.json_mode:
            logger.json_output(res)
        else:
            if res.get("success"):
                logger.success(res.get("message"))
            else:
                logger.error(f"Installation failed: {res.get('error')}")
                if res.get("hint"):
                    logger.hint(f"Hint: {res['hint']}")
        return 0 if res.get("success") else 1

    elif sub == "share":
        target_apk = Path(args.file) if args.file else None
        if not target_apk:
            found = find_apks(cwd)
            if found:
                target_apk = found[0]
            else:
                logger.error("No APK specified and none found in project.")
                return 1

        dest_dir = Path(args.dest) if getattr(args, "dest", None) else None
        res = share_apk(target_apk, dest_dir=dest_dir)
        if logger.json_mode:
            logger.json_output(res)
        else:
            if res.get("success"):
                logger.success(res.get("message"))
                logger.detail("Destination", res.get("destination"))
            else:
                logger.error(f"Share failed: {res.get('error')}")
                if res.get("hint"):
                    logger.hint(f"Hint: {res['hint']}")
        return 0 if res.get("success") else 1

    elif sub == "sign":
        target_apk = Path(args.file) if args.file else None
        if not target_apk:
            found = find_apks(cwd)
            if found:
                target_apk = found[0]
            else:
                logger.error("No APK specified and none found in project.")
                return 1

        ks = Path(args.keystore) if getattr(args, "keystore", None) else None
        res = sign_apk(target_apk, keystore=ks, key_alias=getattr(args, "alias", None))
        if logger.json_mode:
            logger.json_output(res)
        else:
            if res.get("success"):
                logger.success(res.get("message"))
                logger.detail("Keystore", res.get("keystore"))
            else:
                logger.error(f"Sign failed: {res.get('error')}")
                if res.get("hint"):
                    logger.hint(f"Hint: {res['hint']}")
        return 0 if res.get("success") else 1

    elif sub == "clean":
        apks = find_apks(cwd)
        removed = 0
        failures = []
        for apk in apks:
            try:
                apk.unlink()
                removed += 1
            except OSError as exc:
                failures.append({"path": str(apk), "error": str(exc)})
        result = {
            "success": not failures,
            "removed": removed,
            "failed": len(failures),
            "errors": failures,
        }
        if failures:
            result["error"] = f"Could not remove {len(failures)} APK file(s)."
            result["error_code"] = "apk_clean_partial"
        if logger.json_mode:
            logger.json_output(result)
        elif failures:
            logger.warn(f"Removed {removed} APK file(s), but {len(failures)} could not be removed.")
            for failure in failures:
                logger.error(f"{failure['path']}: {failure['error']}")
        else:
            logger.success(f"Removed {removed} APK file(s).")
        return 0 if not failures else 1
    return 0


def handle_deps(args) -> int:
    from wobble.deps.manager import deps_install, deps_add, deps_remove, deps_doctor, deps_list

    sub = args.subcommand or "doctor"
    cwd = Path.cwd()
    logger = get_logger()

    def finish_operation(res):
        if logger.json_mode:
            logger.json_output(res)
        elif not res.get("success"):
            logger.error(res.get("error") or res.get("stderr") or "Dependency operation failed.")
            if res.get("hint"):
                logger.hint(res["hint"])
        return 0 if res.get("success") else 1

    if sub == "install":
        return finish_operation(deps_install(args.target, cwd))

    elif sub == "add":
        return finish_operation(deps_add(args.package, args.manager, cwd))

    elif sub == "remove":
        return finish_operation(deps_remove(args.package, args.manager, cwd))

    elif sub == "doctor":
        res = deps_doctor(cwd)
        if get_logger().json_mode:
            get_logger().json_output(res)
        else:
            get_logger().heading(f"Dependency Health: {res['project']}")
            if res["status"] == "ok":
                get_logger().success("All project dependencies appear healthy.")
            else:
                for issue in res["issues"]:
                    get_logger().warn(issue["message"])
                    print(f"      Fix: {issue['fix']}")
            print()
        return 0

    elif sub == "list":
        res = deps_list(cwd)
        if get_logger().json_mode:
            get_logger().json_output(res)
        else:
            get_logger().heading(f"Dependencies: {res['project']}")
            if res.get("dependencies"):
                print("  Dependencies:")
                for k, v in res["dependencies"].items():
                    print(f"    - {k}: {v}")
            if res.get("dev_dependencies"):
                print("  Dev Dependencies:")
                for k, v in res["dev_dependencies"].items():
                    print(f"    - {k}: {v}")
            if res.get("system"):
                print("  System Packages:")
                for s in res["system"]:
                    print(f"    - {s}")
            for issue in res.get("errors", []):
                get_logger().error(f"Cannot read {issue['path']}: {issue['error']}")
            print()
        return 0 if res.get("success", True) else 1
    return 0


def handle_plugin(args) -> int:
    from wobble.plugins.loader import list_plugins, get_plugin

    logger = get_logger()
    sub = args.subcommand or "list"

    if sub == "list":
        plugins = list_plugins()
        if logger.json_mode:
            logger.json_output({"plugins": [p.to_dict() for p in plugins], "count": len(plugins)})
        else:
            logger.heading("Available Framework Plugins")
            from wobble.core import theme
            for p in plugins:
                cat = theme.paint(f"[{p.category}]", theme.DIM, enabled=logger.use_color)
                name = theme.paint(f"{p.name:<16}", theme.BOLD, enabled=logger.use_color)
                arrow = theme.paint("->", theme.CYAN, enabled=logger.use_color)
                print(f"  {arrow} {name} {cat:<10} - {p.description}")
            print()
        return 0

    elif sub == "info":
        p = get_plugin(args.name)
        if not p:
            available = [pl.name for pl in list_plugins()]
            logger.error(f"Plugin '{args.name}' not found.{_suggest_names(args.name, available)}")
            return 1
        if logger.json_mode:
            logger.json_output(p.to_dict())
        else:
            logger.heading(f"Plugin: {p.name}")
            logger.detail("Version", p.version)
            logger.detail("Category", p.category)
            logger.detail("Description", p.description)
            logger.detail("Required Tools", ", ".join(p.required_tools) if p.required_tools else "None")
            logger.detail("Termux Packages", ", ".join(p.required_system_packages) if p.required_system_packages else "None")
            prereq = p.check_prerequisites()
            logger.detail("Ready on Host", "Yes" if prereq["ready"] else f"Missing: {prereq['missing_tools']}")
            print()
        return 0
    return 0


def handle_config(args) -> int:
    from wobble.core.config import get_config, DEFAULT_CONFIG

    logger = get_logger()
    cfg = get_config()
    sub = args.subcommand or "list"
    for warning in cfg.warnings:
        logger.warn(warning)

    if sub == "list":
        if logger.json_mode:
            logger.json_output(cfg.all())
        else:
            logger.heading("Wobble Configuration Settings")
            for k, v in cfg.all().items():
                print(f"  {k:<26} = {v}")
            print()
        return 0
    elif sub == "get":
        if args.key not in cfg.all():
            logger.error(f"Configuration key '{args.key}' is not set.{_suggest_names(args.key, cfg.all().keys())}")
            return 1
        val = cfg.get(args.key)
        if logger.json_mode:
            logger.json_output({args.key: val})
        else:
            print(f"{args.key} = {val}")
        return 0
    elif sub == "set":
        if args.key not in DEFAULT_CONFIG:
            logger.warn(
                f"'{args.key}' is not a standard setting.{_suggest_names(args.key, DEFAULT_CONFIG.keys())}"
            )
        cfg.set(args.key, args.value)
        if logger.json_mode:
            logger.json_output({"status": "updated", args.key: args.value})
        else:
            logger.success(f"Config '{args.key}' set to '{args.value}'")
        return 0
    return 0


def handle_clean(args) -> int:
    """Remove build artifacts and caches; --all also drops heavyweight dependencies."""
    import shutil

    logger = get_logger()
    cwd = Path.cwd()

    artifact_dirs = {"build", "dist", "out", ".vite", "__pycache__", ".pytest_cache", ".next", "coverage"}
    deep_dirs = {"node_modules", ".gradle", ".venv", ".tox"}
    deep = bool(getattr(args, "all", False))

    targets: List[Path] = []
    skip_walk = {".git", ".wobble"}
    if not deep:
        skip_walk |= deep_dirs

    for dirpath, dirnames, filenames in os.walk(cwd):
        dirnames[:] = [d for d in dirnames if d not in skip_walk]
        for d in list(dirnames):
            if d in artifact_dirs or (deep and d in deep_dirs):
                candidate = Path(dirpath) / d
                dirnames.remove(d)  # don't descend into what we delete
                # Never delete through a symlink: it could point outside the project.
                if candidate.is_symlink():
                    continue
                targets.append(candidate)
        for f in filenames:
            if f.endswith(".apk"):
                targets.append(Path(dirpath) / f)

    if not targets:
        if logger.json_mode:
            logger.json_output({"removed": 0, "status": "already clean"})
        else:
            logger.success("Nothing to clean. Workspace is already tidy.")
        return 0

    # Deep cleans destroy dependencies and long build caches: confirm on interactive terminals
    if deep and not getattr(args, "yes", False) and not logger.json_mode and sys.stdin.isatty():
        logger.warn(f"Deep clean will permanently delete {len(targets)} item(s), including node_modules / Gradle caches:")
        for t in targets[:8]:
            logger.detail("will remove", str(t.relative_to(cwd)))
        if len(targets) > 8:
            logger.detail("...", f"and {len(targets) - 8} more")
        try:
            answer = input("Continue? [y/N] ").strip().lower()
        except EOFError:
            answer = ""
        if answer not in ("y", "yes"):
            logger.info("Clean cancelled.")
            return 0

    removed = 0
    freed = 0
    failures = []
    for target in targets:
        try:
            if target.is_file() or target.is_symlink():
                try:
                    freed += target.stat().st_size
                except OSError:
                    pass
                target.unlink()
            elif target.is_dir():
                for dirpath, dirnames, filenames in os.walk(target):
                    for filename in filenames:
                        try:
                            freed += (Path(dirpath) / filename).stat().st_size
                        except OSError:
                            pass
                # Never use ignore_errors=True and then claim success.
                shutil.rmtree(target)
            else:
                # It disappeared between discovery and deletion.
                continue
            removed += 1
        except OSError as exc:
            failures.append({"path": str(target), "error": str(exc)})

    result = {
        "success": not failures,
        "removed": removed,
        "failed": len(failures),
        "freed_bytes": freed,
        "errors": failures,
    }
    if failures:
        result["error"] = f"Clean completed with {len(failures)} error(s)."
        result["error_code"] = "clean_partial"
    if logger.json_mode:
        logger.json_output(result)
    elif failures:
        logger.warn(f"Removed {removed} item(s), but {len(failures)} item(s) could not be removed.")
        for failure in failures:
            logger.error(f"{failure['path']}: {failure['error']}")
    else:
        logger.success(f"Removed {removed} item(s), freeing {round(freed / (1024 * 1024), 1)} MB.")
    return 0 if not failures else 1


def handle_completion(args) -> int:
    from wobble.core.completions import COMPLETIONS

    logger = get_logger()
    shell = getattr(args, "shell", "bash") or "bash"
    script = COMPLETIONS.get(shell, COMPLETIONS["bash"])
    if logger.json_mode:
        logger.json_output({"shell": shell, "script": script})
    else:
        print(script)
    return 0


def _human_bytes(num: int) -> str:
    value = float(max(0, num))
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024.0
    return f"{value:.1f} GB"


def handle_banner(args) -> int:
    from wobble.core import theme

    logger = get_logger()
    if logger.json_mode:
        logger.json_output({"banner": theme.BANNER_ART, "tagline": theme.TAGLINE,
                            "version": __version__})
        return 0
    logger.banner(theme.TAGLINE)
    print()
    return 0


def handle_about(args) -> int:
    from wobble.core import installer, theme
    from wobble.core.context import get_architecture, get_home, get_prefix, is_termux

    logger = get_logger()
    info = installer.status()
    mode = "standalone install" if info.get("standalone") else info.get("mode", "source checkout")
    if info.get("installed") and info.get("source_exists") is False:
        independence = "yes (source checkout deleted)"
    elif info.get("standalone"):
        independence = "yes"
    else:
        independence = "no (runs from source checkout)"

    rows = [
        theme.kv("version", __version__, use_color=logger.use_color),
        theme.kv("install", mode, use_color=logger.use_color),
        theme.kv("location", info.get("app_dir") or str(Path(__file__).resolve().parents[1]),
                 use_color=logger.use_color),
        theme.kv("source-free", independence, use_color=logger.use_color),
        theme.kv("python", sys.version.split()[0], use_color=logger.use_color),
        theme.kv("platform", f"{get_architecture()} | termux={str(is_termux()).lower()}",
                 use_color=logger.use_color),
        theme.kv("prefix", str(get_prefix()), use_color=logger.use_color),
        theme.kv("home", str(get_home()), use_color=logger.use_color),
    ]
    if logger.json_mode:
        logger.json_output({
            "version": __version__,
            "install": info,
            "python": sys.version.split()[0],
            "architecture": get_architecture(),
            "termux": is_termux(),
            "prefix": str(get_prefix()),
            "home": str(get_home()),
        })
        return 0

    logger.banner(theme.TAGLINE)
    print()
    print(theme.box(f"about wobble v{__version__}", rows, width=70, use_color=logger.use_color))
    print()
    return 0


def _self_targets(args):
    """Resolve --root/--bin overrides shared by every self subcommand."""
    root = Path(args.root).expanduser() if getattr(args, "root", None) else None
    bin_dir = Path(getattr(args, "bin", None)).expanduser() if getattr(args, "bin", None) else None
    return root, bin_dir


def _self_status(args) -> int:
    from wobble.core import selfcheck, theme

    logger = get_logger()
    root, bin_dir = _self_targets(args)
    report = selfcheck.inspect(
        deep=bool(getattr(args, "deep", False)),
        install_root=root,
        bin_dir=bin_dir,
    )
    code = selfcheck.exit_code(report, strict=bool(getattr(args, "strict", False)))

    if logger.json_mode:
        report["exit_code"] = code
        logger.json_output(report)
        return code

    if getattr(args, "brief", False):
        counts = report["counts"]
        overall = "ok" if report["ok"] else (
            "error" if report["status"] == "broken" else "warning")
        print(f"{theme.badge(overall, logger.use_color)} "
              f"{report['status']}  {report['mode']} v{report['version']}  "
              f"{counts['ok']} ok, {counts['warning']} warnings, {counts['critical']} critical"
              f"  ({report['elapsed_ms']} ms)")
        return code

    print(selfcheck.render(report, use_color=logger.use_color))
    if report["mode"] == "source-checkout":
        print()
        logger.hint("Running from a source checkout; install it with: wob self install")
    elif report["mode"] == "legacy-symlink":
        print()
        logger.warn("Legacy symlink install: deleting the checkout would break 'wob'.")
        logger.hint("Switch to a standalone install with: wob self install")
    print()
    return code


def _self_verify(args) -> int:
    from wobble.core import installer, theme

    logger = get_logger()
    root, bin_dir = _self_targets(args)
    data = installer.verify(root, parallel=not bool(getattr(args, "serial", False)))
    launcher_path = Path(data.get("launcher") or (bin_dir or installer.default_bin_dir()) / "wob")
    launcher_state = installer._launcher_state(launcher_path)
    strict = bool(getattr(args, "strict", False))
    if strict and data.get("ok") and not launcher_state.get("executable"):
        data["ok"] = False
        data["launcher_ok"] = False
        data["hint"] = "Launcher is not executable: chmod 755 " + str(launcher_path)

    if logger.json_mode:
        data["success"] = bool(data.get("ok"))
        if not data["success"]:
            if data.get("error"):
                data.setdefault("error_code", "installation_manifest_missing")
            else:
                data["error"] = "Installed files failed integrity verification."
                data["error_code"] = "installation_verification_failed"
        data["launcher"] = str(launcher_path)
        data["launcher_state"] = launcher_state
        logger.json_output(data)
        return 0 if data.get("ok") else 1

    print(theme.rule("installation integrity", width=66, use_color=logger.use_color))
    if data.get("error"):
        logger.status("warning", "manifest", data["error"])
        logger.hint(data.get("hint") or "Install Wobble with: sh install.sh")
        print()
        return 1

    logger.status("ok" if data.get("ok") else "error", "manifest",
                  f"{data.get('checked', 0)}/{data.get('file_count', 0)} files verified "
                  f"in {data.get('elapsed_ms', 0)} ms")
    logger.detail("Hashed", _human_bytes(data.get("hashed_bytes", 0)))
    logger.detail("Parallel", "yes" if data.get("parallel") else "no (small tree)")
    for rel in data.get("missing", [])[:8]:
        logger.detail("missing", rel)
    for rel in data.get("modified", [])[:8]:
        logger.detail("modified", rel)
    for rel in data.get("unreadable", [])[:8]:
        logger.detail("unreadable", rel)
    if not data.get("launcher_ok", True):
        logger.warn("Launcher missing, replaced, or not executable; run 'wob self repair'.")
    if data.get("running_version") and data.get("version") != data.get("running_version"):
        logger.warn(f"Manifest version v{data.get('version')} != running v{data.get('running_version')}")
    if data.get("ok"):
        logger.success("Every installed file matches the manifest.")
    else:
        logger.hint("Reinstall a verified runtime with: wob self install")
        logger.hint("If you patched the install on purpose: wob self repair --accept-current")
    print()
    return 0 if data.get("ok") else 1


def _self_repair(args) -> int:
    from wobble.core import selfcheck, theme

    logger = get_logger()
    root, bin_dir = _self_targets(args)
    accept_current = bool(getattr(args, "accept_current", False))
    assume_yes = bool(getattr(args, "yes", False))

    if accept_current and not assume_yes:
        if logger.json_mode or not sys.stdin.isatty():
            logger.error("--accept-current rewrites integrity hashes; re-run with --yes.")
            return 1
        logger.warn("--accept-current treats the current runtime files as trusted.")
        try:
            answer = input("Re-baseline manifest hashes? [y/N] ").strip().lower()
        except EOFError:
            answer = ""
        if answer not in ("y", "yes"):
            logger.info("Repair cancelled.")
            return 0

    data = selfcheck.repair(
        install_root=root,
        bin_dir=bin_dir,
        compile_bytecode=bool(getattr(args, "compile", True)),
        completions=bool(getattr(args, "completions", True)),
        update_path=bool(getattr(args, "path", False)),
        fix_config=bool(getattr(args, "fix_config", True)),
        accept_current=accept_current,
    )

    if logger.json_mode:
        logger.json_output(data)
        return 0 if data.get("success") else 1

    print(theme.rule("self repair", width=66, use_color=logger.use_color))
    if data.get("error"):
        logger.error(data["error"])
        if data.get("fix"):
            logger.hint(data["fix"])
        print()
        return 1
    if not data.get("actions"):
        logger.info("Nothing needed repair.")
    for action in data.get("actions", []):
        name = action.get("action")
        if name == "rewrite_launchers":
            logger.status("ok", "launchers", ", ".join(action.get("written", [])) or "none")
        elif name == "compile_bytecode":
            logger.status("ok", "bytecode", f"{action.get('pyc_files', 0)} .pyc files")
        elif name == "cleanup_leftovers":
            logger.status("ok", "debris", f"removed {len(action.get('removed', []))} path(s)")
        elif name == "install_completions":
            logger.status("ok", "completions", f"{len(action.get('written', []))} file(s)")
        elif name.startswith("backup_corrupt_"):
            logger.status("warning", name.replace("backup_corrupt_", "corrupt "),
                          f"backed up to {action.get('backup')}")
        elif name == "update_shell_path":
            logger.status("ok", "PATH", ", ".join(action.get("touched", [])) or "already configured")
        elif name == "refresh_manifest":
            logger.status("ok", "manifest", f"re-baselined {action.get('file_count', 0)} files")
        else:
            logger.status("ok", name, "")
    for failure in data.get("failed", []):
        logger.error(f"{failure.get('action')}: {failure.get('error')}")
    for problem in data.get("unresolved", []):
        logger.warn(f"{problem['problem']} -> {problem['fix']}")
    if data.get("success"):
        logger.success("Installation repaired and verified.")
    print()
    return 0 if data.get("success") else 1


def _self_watch(args) -> int:
    import json
    import time

    from wobble.core import selfcheck

    logger = get_logger()
    root, bin_dir = _self_targets(args)
    interval = max(0.2, float(getattr(args, "interval", 2.0) or 2.0))
    remaining = int(getattr(args, "count", 0) or 0)
    deep = bool(getattr(args, "deep", False))

    if not logger.json_mode:
        print(f"[wob] watching installation health every {interval:g}s "
              f"({'deep' if deep else 'fast'}; Ctrl+C to stop)", flush=True)

    previous = None
    tick = 0
    try:
        while True:
            tick += 1
            report = selfcheck.inspect(deep=deep, install_root=root, bin_dir=bin_dir)
            snapshot = {c["code"]: c["status"] for c in report["checks"]}
            changes = []
            if previous is not None:
                rank = selfcheck.RANK
                for code in sorted(set(previous) | set(snapshot)):
                    before = previous.get(code)
                    after = snapshot.get(code)
                    if before == after:
                        continue
                    if before is None:
                        kind = "new"
                    elif after is None:
                        kind = "gone"
                    elif rank.get(after, 1) > rank.get(before, 1):
                        kind = "worsened"
                    else:
                        kind = "recovered"
                    changes.append({"change": kind, "code": code,
                                    "from": before, "to": after})
            stamp = time.strftime("%H:%M:%S")
            if logger.json_mode:
                print(json.dumps({
                    "tick": tick,
                    "time": stamp,
                    "status": report["status"],
                    "counts": report["counts"],
                    "elapsed_ms": report["elapsed_ms"],
                    "changes": changes,
                    "issues": [{"code": i["code"], "status": i["status"],
                                "detail": i["detail"], "fix": i.get("fix")}
                               for i in report["issues"]],
                }, default=str), flush=True)
            elif changes:
                for change in changes:
                    before = change["from"] or "absent"
                    after = change["to"] or "absent"
                    print(f"[{stamp}] {change['change']:<9} {change['code']}: "
                          f"{before} -> {after}", flush=True)
                if any(change["change"] in ("new", "worsened") and change["to"] == "critical"
                       for change in changes):
                    print(f"[{stamp}] fix: wob self repair", flush=True)
            else:
                print(f"[{stamp}] {report['status']}  "
                      f"{report['counts']['ok']} ok, {report['counts']['warning']} warnings, "
                      f"{report['counts']['critical']} critical  ({report['elapsed_ms']} ms)",
                      flush=True)
            previous = snapshot
            remaining -= 1
            if remaining == 0:
                break
            time.sleep(interval)
    except KeyboardInterrupt:
        if not logger.json_mode:
            print()
            print("Stopped watching.")
    return 0


def _self_incidents(args) -> int:
    from wobble.core import health, theme

    logger = get_logger()
    limit = max(1, int(getattr(args, "limit", 10) or 10))
    summary = health.incident_summary(limit=limit)
    incidents = health.read_incidents(limit=limit)

    if logger.json_mode:
        payload = dict(summary)
        payload["incidents"] = incidents
        payload["cleared"] = 0
        if getattr(args, "clear", False):
            payload["cleared"] = health.clear_incidents()
        logger.json_output(payload)
        return 0

    print(theme.rule("failure ledger", width=66, use_color=logger.use_color))
    if not incidents:
        logger.status("ok", "incidents", "none recorded")
    else:
        for incident in incidents:
            stamp = incident.get("last_seen_iso", "?")
            count = incident.get("count", 1)
            logger.status("warning" if incident.get("kind") != "crash" else "error",
                          f"{incident.get('kind')} x{count}",
                          f"{stamp}  {incident.get('message', '')[:120]}")
    if getattr(args, "clear", False):
        cleared = health.clear_incidents()
        logger.status("ok", "cleared", f"{cleared} incident(s)")
    elif incidents:
        logger.hint("Clear with: wob self incidents --clear")
    print()
    return 0


def handle_self(args) -> int:
    sub = getattr(args, "subcommand", None) or "status"
    if sub in ("status", "health"):
        return _self_status(args)
    if sub == "verify":
        return _self_verify(args)
    if sub == "repair":
        return _self_repair(args)
    if sub == "watch":
        return _self_watch(args)
    if sub == "incidents":
        return _self_incidents(args)
    if sub == "install":
        return _do_install(args)
    if sub == "uninstall":
        return _do_uninstall(args)
    get_logger().error(f"Unknown self subcommand: {sub}")
    return 1


def _do_install(args) -> int:
    from wobble.core import installer, theme

    logger = get_logger()
    try:
        data = installer.install(
            source_root=installer.package_root(),
            install_root=Path(args.root).expanduser() if getattr(args, "root", None) else None,
            bin_dir=Path(args.bin).expanduser() if getattr(args, "bin", None) else None,
            force=bool(getattr(args, "force", False)),
            completions=not getattr(args, "no_completion", False),
            update_path=not getattr(args, "no_path", False),
        )
    except installer.InstallerError as exc:
        logger.error(str(exc))
        return 1

    if logger.json_mode:
        logger.json_output(data)
        return 0

    if not os.environ.get("WOBBLE_INSTALL_QUIET"):
        logger.banner(theme.TAGLINE)
        print()
    print(theme.rule("installed", width=64, use_color=logger.use_color))
    logger.status("ok", "version", data["version"])
    logger.detail("App dir", data["app_dir"])
    logger.detail("Launcher", data["launcher"])
    logger.detail("Files", f"{data['file_count']} ({_human_bytes(data['total_bytes'])})")
    logger.detail("Time", f"{data['elapsed_seconds']}s")
    if data.get("completions"):
        logger.detail("Completions", ", ".join(data["completions"]))
    if data.get("shell_configs"):
        logger.detail("PATH updated", ", ".join(data["shell_configs"]))
    print()
    logger.success("Wobble now runs from its own app directory; the source checkout is optional.")
    logger.hint("Open a new terminal (or 'source ~/.bashrc') and run: wob self verify")
    print()
    return 0


def _do_uninstall(args) -> int:
    from wobble.core import installer, theme

    logger = get_logger()
    root = Path(args.root).expanduser() if getattr(args, "root", None) else None
    purge = bool(getattr(args, "purge", False))
    assume_yes = bool(getattr(args, "yes", False))
    target = root or installer.default_install_root()

    if not assume_yes and not logger.json_mode:
        if not sys.stdin.isatty():
            logger.error("Refusing to uninstall without confirmation. Re-run with --yes.")
            return 1
        logger.warn(f"This removes Wobble from {target}. Your project folders are preserved.")
        try:
            answer = input("Remove Wobble? [y/N] ").strip().lower()
        except EOFError:
            answer = ""
        if answer not in ("y", "yes"):
            logger.info("Uninstall cancelled.")
            return 0

    data = installer.uninstall(root, purge=purge)
    if logger.json_mode:
        logger.json_output(data)
        return 0

    print(theme.rule("uninstalled", width=64, use_color=logger.use_color))
    for path in data.get("removed", []):
        logger.detail("removed", path)
    for path in data.get("purged", []):
        logger.detail("purged", path)
    logger.success("Wobble has been removed. Project directories and APKs were untouched.")
    if not purge:
        logger.hint("Config/cache kept in ~/.wobble and ~/.config/wobble (use --purge to remove).")
    print()
    return 0


def handle_install(args) -> int:
    return _do_install(args)


def handle_uninstall(args) -> int:
    return _do_uninstall(args)


def handle_update(args) -> int:
    from wobble.core import installer

    logger = get_logger()
    info = installer.status()
    if logger.json_mode:
        logger.json_output({
            "version": __version__,
            "installed": bool(info.get("installed")),
            "mode": info.get("mode"),
            "upgrade": "sh install.sh" if info.get("standalone") else "git pull && sh install.sh",
        })
        return 0
    logger.heading("Wobble Updates")
    logger.detail("Installed version", f"v{__version__}")
    logger.detail("Install mode", info.get("mode"))
    logger.info("Upgrade by re-running the installer from a fresh checkout:")
    logger.detail("Upgrade", "git pull && sh install.sh")
    logger.hint("Reinstalling keeps your projects, registry, config, and keystore.")
    print()
    return 0


_GLOBAL_FLAGS = {"--json", "--no-color", "-v", "--verbose"}
# Global flag hoisting must not steal a token that belongs to another option.
# Keep this list in sync with value-taking options in build_parser().
_OPTIONS_WITH_VALUES = {
    "-f", "--framework", "-p", "--package", "--port", "-d", "--dir",
    "--path", "--host", "--dest", "--keystore", "--alias", "--method",
    "-m", "--manager", "--root", "--bin", "--only", "--fail-on",
    "--interval", "--count", "--limit",
}


def _hoist_global_flags(argv: List[str]) -> List[str]:
    """Allow global flags before *or* after the subcommand.

    argparse only understands `wob --json doctor`, but users (and the docs)
    naturally write `wob doctor --json`. Move recognised global flags in front
    of the command, leaving everything after `--` untouched. The transformation
    is stable and idempotent: flags already in front keep their order.
    """
    flags: List[str] = []
    rest: List[str] = []
    seen_dashdash = False
    expects_value = False
    for token in argv:
        if seen_dashdash:
            rest.append(token)
            continue
        if expects_value:
            # This token is data, even when it is spelled --json or -v.
            rest.append(token)
            expects_value = False
            continue
        if token == "--":
            seen_dashdash = True
            rest.append(token)
            continue
        if token in _OPTIONS_WITH_VALUES:
            rest.append(token)
            expects_value = True
            continue
        if token in _GLOBAL_FLAGS:
            if token not in flags:
                flags.append(token)
            continue
        rest.append(token)
    return flags + rest


def _leading_global_flags(argv: List[str]) -> set:
    """Return only hoisted flags, not lookalikes retained as option values."""
    leading = set()
    for token in argv:
        if token not in _GLOBAL_FLAGS:
            break
        leading.add(token)
    return leading


def _report_error(logger: Logger, error: WobbleError) -> None:
    """Render an expected error once, respecting the output contract."""
    import json

    if logger.json_mode:
        if not logger._json_emitted:
            logger.json_output(error.to_dict())
        else:
            # A long-running command may already have emitted its startup
            # document. Preserve stdout as valid JSON but never lose a later
            # failure: send a compact diagnostic document to stderr.
            print(json.dumps(error.to_dict(), default=str), file=sys.stderr)
        return
    usage = error.details.get("usage") if isinstance(error, UsageError) else None
    if usage:
        print(usage, file=sys.stderr)
    logger.error(error.message)
    if error.hint:
        print(f"Hint: {error.hint}", file=sys.stderr)


def main(argv: Optional[List[str]] = None) -> int:
    argv = _hoist_global_flags(list(sys.argv[1:] if argv is None else argv))

    # Initialize output before parsing so malformed arguments also honor real
    # global flags (but not --json/-v tokens consumed as another option's value).
    global_flags = _leading_global_flags(argv)
    logger = Logger(json_mode="--json" in global_flags, no_color="--no-color" in global_flags)
    set_logger(logger)
    verbose = "--verbose" in global_flags or "-v" in global_flags

    try:
        # Bare `wob` never needs argparse, but it gets the same broken-pipe and
        # unexpected-error protection as every parsed command.
        if not argv:
            from wobble.bootstrap import print_landing
            print_landing()
            return 0

        parser = build_parser()
        args = parser.parse_args(argv)

        if not args.command:
            if logger.json_mode:
                logger.json_output({
                    "name": "wobble",
                    "command": "wob",
                    "version": __version__,
                    "hint": "Run 'wob --help' or 'wob schema' for the full command list.",
                })
            else:
                parser.print_help()
            return 0

        exit_code = _dispatch(parser, args)
        if not isinstance(exit_code, int):
            raise WobbleError(
                f"Command '{args.command}' did not return a valid exit status.",
                code="invalid_exit_status",
            )
        # A signal can be reported by subprocess APIs as -SIG. Shells expect
        # 128+SIG, never Python's platform-dependent wrapping of a negative exit.
        if exit_code < 0:
            exit_code = 128 - exit_code

        if exit_code != 0 and logger.json_mode and not logger._json_emitted:
            message = (
                logger.errors[-1]
                if logger.errors
                else f"Command '{args.command}' failed with exit code {exit_code}."
            )
            logger.json_output(WobbleError(
                message,
                code="command_failed",
                details={"exit_code": exit_code},
            ).to_dict())
        return exit_code
    except KeyboardInterrupt:
        if logger.json_mode:
            if not logger._json_emitted:
                logger.json_output({
                    "success": False,
                    "error": "Interrupted by user.",
                    "error_code": "interrupted",
                    "details": {"exit_code": EXIT_INTERRUPTED},
                })
        else:
            print("\nInterrupted.", file=sys.stderr)
        return EXIT_INTERRUPTED
    except BrokenPipeError:
        # Allow piping into head/tail without closing a caller-owned stream.
        return 0
    except WobbleError as exc:
        if verbose:
            import traceback
            traceback.print_exc()
        _report_error(logger, exc)
        return exc.exit_code
    except Exception as exc:
        if verbose:
            import traceback
            traceback.print_exc()
        try:
            from wobble.core import health
            health.record_incident(
                "crash",
                f"{type(exc).__name__}: {exc}",
                {"command": " ".join(argv[:4]), "version": __version__},
            )
        except Exception:
            pass
        if logger.json_mode:
            payload = unexpected_error_payload(exc, verbose=verbose)
            if not logger._json_emitted:
                logger.json_output(payload)
            else:
                import json
                print(json.dumps(payload, default=str), file=sys.stderr)
        else:
            logger.error(f"Unexpected error: {exc}")
            logger.info("Run with --verbose for a full traceback, or 'wob doctor' to check your environment.")
        return EXIT_FAILURE


def _dispatch(parser: argparse.ArgumentParser, args) -> int:
    """Route a parsed command to its handler. Heavy modules load only when needed."""
    logger = get_logger()
    cmd = args.command

    # Top-level commands
    if cmd == "doctor":
        from wobble.core.doctor import run_doctor
        fail_on = "warning" if getattr(args, "strict", False) else getattr(args, "fail_on", "never")
        try:
            report = run_doctor(
                json_mode=args.json,
                quick=getattr(args, "quick", False),
                only=getattr(args, "only", None),
                fail_on=fail_on,
                timings=getattr(args, "timings", False),
                no_cache=getattr(args, "no_cache", False),
                save_baseline=getattr(args, "save_baseline", False),
                save=not getattr(args, "no_save", False),
            )
        except ValueError as exc:
            logger.error(str(exc))
            return 2
        return int(report.get("exit_code", 0))

    elif cmd == "schema":
        from wobble.core.schema import get_cli_schema
        import json
        schema_data = get_cli_schema()
        print(json.dumps(schema_data, indent=2))
        return 0

    elif cmd == "completion":
        return handle_completion(args)

    elif cmd == "clean":
        return handle_clean(args)

    elif cmd == "version":
        print(f"Wobble v{__version__}")
        return 0

    elif cmd == "help":
        parser.print_help()
        return 0

    elif cmd == "update":
        return handle_update(args)

    elif cmd == "banner":
        return handle_banner(args)

    elif cmd == "about":
        return handle_about(args)

    elif cmd == "self":
        return handle_self(args)

    elif cmd == "install":
        return handle_install(args)

    elif cmd == "uninstall":
        return handle_uninstall(args)

    # Smart shortcuts
    elif cmd == "build":
        from wobble.project.manager import find_current_project
        spec = find_current_project()
        if spec and spec.project_type == "android":
            from wobble.android.manager import build_android
            res = build_android(Path.cwd(), release=args.release)
        else:
            from wobble.web.manager import run_web_build
            res = run_web_build(Path.cwd())
        if logger.json_mode:
            logger.json_output(res)
        elif not res.get("success") and not logger.errors:
            logger.error(res.get("error") or res.get("stderr") or "Build failed.")
        return 0 if res.get("success") else 1

    elif cmd == "dev":
        from wobble.web.manager import run_web_dev
        return run_web_dev(Path.cwd(), port=args.port, host=_resolve_host(args))

    elif cmd == "preview":
        from wobble.web.manager import run_web_preview
        return run_web_preview(Path.cwd(), port=args.port, host=_resolve_host(args))

    # Subcommand routing
    elif cmd == "create":
        return handle_create(args)
    elif cmd == "project":
        return handle_project(args)
    elif cmd == "android":
        return handle_android(args)
    elif cmd == "web":
        return handle_web(args)
    elif cmd == "apk":
        return handle_apk(args)
    elif cmd == "deps":
        return handle_deps(args)
    elif cmd == "plugin":
        return handle_plugin(args)
    elif cmd == "config":
        return handle_config(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
