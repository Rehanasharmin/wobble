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
from wobble.core.logger import Logger, set_logger, get_logger

# NOTE: heavyweight subcommand modules (doctor, apk, web, deps, plugins) are
# imported lazily inside their handlers. This keeps 'wob --version' and other
# trivial commands fast on mobile CPUs where import time is noticeable.


def build_parser() -> argparse.ArgumentParser:
    """Construct the main argument parser for Wobble CLI."""
    parser = argparse.ArgumentParser(
        prog="wob",
        description="Wobble - the Termux development harness for Android and web projects",
        epilog="""examples:
  wob doctor                        audit the environment before building
  wob create android myapp          scaffold a native Android project
  wob create web site -f react      scaffold a React web project
  wob apk build && wob apk install  build and install a debug APK
  wob web preview --lan             preview on localhost and your Wi-Fi
  wob self status                   verify the standalone installation
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
    p_web_dev.add_argument("-p", "--port", type=int, help="Port to listen on")
    p_web_dev.add_argument("--host", default=None, help="Host address to bind (default: 127.0.0.1)")
    p_web_dev.add_argument("--lan", action="store_true", help="Expose the dev server on your LAN (0.0.0.0)")
    sp_web.add_parser("build", help="Build web application for distribution")
    sp_web.add_parser("test", help="Run web test suite")
    p_web_prev = sp_web.add_parser("preview", help="Start the hardened preview server (localhost by default)")
    p_web_prev.add_argument("-p", "--port", type=int, help="Port to serve on")
    p_web_prev.add_argument("--dir", help="Directory to serve")
    p_web_prev.add_argument("--host", default=None, help="Host address to bind (default: 127.0.0.1)")
    p_web_prev.add_argument("--lan", action="store_true", help="Expose the preview on your LAN (0.0.0.0)")
    p_web_serve = sp_web.add_parser("serve", help="Static HTTP file server")
    p_web_serve.add_argument("-p", "--port", type=int, help="Port to serve on")
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
    p_doctor = subparsers.add_parser("doctor", help="Run comprehensive environment health diagnostics")
    p_doctor.add_argument("--quick", action="store_true", help="Skip slow tool version probes")

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

    # 11. wob self (install/uninstall/verify the application itself)
    p_self = subparsers.add_parser("self", help="Install, verify, or uninstall Wobble itself")
    sp_self = p_self.add_subparsers(dest="subcommand")
    sp_self.add_parser("status", help="Show how Wobble is installed")
    sp_self.add_parser("verify", help="Verify installed files against the manifest")
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
    p_dev.add_argument("-p", "--port", type=int, help="Port to listen on")
    p_dev.add_argument("--host", default=None, help="Host address to bind (default: 127.0.0.1)")
    p_dev.add_argument("--lan", action="store_true", help="Expose on LAN (0.0.0.0)")

    p_prev = subparsers.add_parser("preview", help="Preview the current project locally (--lan for Wi-Fi)")
    p_prev.add_argument("-p", "--port", type=int, help="Port to listen on")
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
        register_project(name, target_dir)
        logger.success(f"Project '{name}' successfully created!")
        if not logger.json_mode:
            print("\nNext steps:")
            print(f"  cd {name}")
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
        unregister_project(name)
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
        return 0 if res.get("success") else 1
    elif sub == "test":
        res = run_web_test(cwd)
        if get_logger().json_mode:
            get_logger().json_output(res)
        return 0 if res.get("success") else 1
    elif sub == "preview":
        run_web_preview(cwd, port=args.port, target_sub_dir=args.dir, host=host)
        return 0
    elif sub == "serve":
        run_web_preview(cwd, port=args.port, host=host)
        return 0
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
        return 0 if res.get("success") else 1

    elif sub == "clean":
        apks = find_apks(cwd)
        removed = 0
        for a in apks:
            try:
                a.unlink()
                removed += 1
            except Exception:
                pass
        if logger.json_mode:
            logger.json_output({"removed": removed})
        else:
            logger.success(f"Removed {removed} APK file(s).")
        return 0
    return 0


def handle_deps(args) -> int:
    from wobble.deps.manager import deps_install, deps_add, deps_remove, deps_doctor, deps_list

    sub = args.subcommand or "doctor"
    cwd = Path.cwd()

    if sub == "install":
        res = deps_install(args.target, cwd)
        if get_logger().json_mode:
            get_logger().json_output(res)
        return 0 if res.get("success") else 1

    elif sub == "add":
        res = deps_add(args.package, args.manager, cwd)
        if get_logger().json_mode:
            get_logger().json_output(res)
        return 0 if res.get("success") else 1

    elif sub == "remove":
        res = deps_remove(args.package, args.manager, cwd)
        if get_logger().json_mode:
            get_logger().json_output(res)
        return 0 if res.get("success") else 1

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
            print()
        return 0
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
    for t in targets:
        try:
            if t.is_file():
                freed += t.stat().st_size
                t.unlink()
            elif t.is_dir():
                for dirpath, dirnames, filenames in os.walk(t):
                    for f in filenames:
                        try:
                            freed += (Path(dirpath) / f).stat().st_size
                        except OSError:
                            pass
                shutil.rmtree(t, ignore_errors=True)
            removed += 1
        except OSError:
            pass

    if logger.json_mode:
        logger.json_output({"removed": removed, "freed_bytes": freed})
    else:
        logger.success(f"Removed {removed} item(s), freeing {round(freed / (1024 * 1024), 1)} MB.")
    return 0


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


def handle_self(args) -> int:
    from wobble.core import installer, theme

    logger = get_logger()
    sub = getattr(args, "subcommand", None) or "status"
    root = Path(args.root).expanduser() if getattr(args, "root", None) else None

    if sub == "status":
        data = installer.status(root)
        if logger.json_mode:
            logger.json_output(data)
            return 0
        healthy = data.get("healthy") if data.get("installed") else False
        print(theme.rule("wobble installation", width=64, use_color=logger.use_color))
        logger.status("ok" if data.get("installed") else "warning",
                      "installed", "yes" if data.get("installed") else "no")
        logger.status("ok" if data.get("standalone") else "warning",
                      "standalone", "yes" if data.get("standalone") else "no")
        if data.get("installed"):
            logger.detail("Version", data.get("version"))
            logger.detail("App dir", data.get("app_dir"))
            logger.detail("Launcher", data.get("launcher") or "missing")
            logger.detail("Files", f"{data.get('file_count', 0)} ({_human_bytes(data.get('total_bytes', 0))})")
            logger.detail("Source needed", "no" if not data.get("source_exists") else "not at runtime")
            logger.status("ok" if healthy else "error", "runtime", "intact" if healthy else "damaged")
            if data.get("message"):
                logger.hint(data["message"])
        else:
            logger.warn(data.get("message", "Wobble is not installed as standalone software."))
            if data.get("legacy_target"):
                logger.detail("Legacy target", data["legacy_target"])
            logger.hint("Install it as software with: wob self install  (or: sh install.sh)")
        print()
        return 0

    if sub == "verify":
        data = installer.verify(root)
        if logger.json_mode:
            logger.json_output(data)
            return 0 if data.get("ok") else 1
        print(theme.rule("installation integrity", width=64, use_color=logger.use_color))
        if data.get("error"):
            logger.status("warning", "manifest", data["error"])
            logger.hint("Install Wobble as software with: sh install.sh  (or: wob self install)")
            print()
            return 1
        logger.status("ok" if data.get("ok") else "error", "manifest",
                      f"{data.get('checked', 0)}/{data.get('file_count', 0)} files verified")
        for rel in data.get("missing", [])[:6]:
            logger.detail("missing", rel)
        for rel in data.get("modified", [])[:6]:
            logger.detail("modified", rel)
        if not data.get("launcher_ok", True):
            logger.warn("Launcher missing or replaced; run 'wob self install --force'.")
        logger.hint("Source checkout is irrelevant here: verification reads only the installed app.")
        print()
        return 0 if data.get("ok") else 1

    if sub == "install":
        return _do_install(args)

    if sub == "uninstall":
        return _do_uninstall(args)

    logger.error(f"Unknown self subcommand: {sub}")
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
    for token in argv:
        if token == "--" and not seen_dashdash:
            seen_dashdash = True
            rest.append(token)
            continue
        if not seen_dashdash and token in _GLOBAL_FLAGS:
            if token not in flags:
                flags.append(token)
            continue
        rest.append(token)
    return flags + rest


def main(argv: Optional[List[str]] = None) -> int:
    argv = _hoist_global_flags(list(sys.argv[1:] if argv is None else argv))

    # Bare `wob` never needs argparse: render the ASCII landing screen instead.
    if not argv:
        from wobble.bootstrap import print_landing
        print_landing()
        return 0

    parser = build_parser()
    args = parser.parse_args(argv)

    # Initialize Logger
    logger = Logger(json_mode=args.json, no_color=args.no_color)
    set_logger(logger)

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

    try:
        return _dispatch(parser, args)
    except KeyboardInterrupt:
        if not logger.json_mode:
            print("\nInterrupted.")
        return 130
    except BrokenPipeError:
        # Allow piping into head/tail without a scary traceback
        try:
            sys.stdout.close()
        except Exception:
            pass
        return 0
    except Exception as e:
        if getattr(args, "verbose", False):
            import traceback
            traceback.print_exc()
        logger.error(f"Unexpected error: {e}")
        logger.info("Run with --verbose for a full traceback, or 'wob doctor' to check your environment.")
        return 1


def _dispatch(parser: argparse.ArgumentParser, args) -> int:
    """Route a parsed command to its handler. Heavy modules load only when needed."""
    logger = get_logger()
    cmd = args.command

    # Top-level commands
    if cmd == "doctor":
        from wobble.core.doctor import run_doctor
        run_doctor(json_mode=args.json, quick=getattr(args, "quick", False))
        return 0

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
            return 0 if res.get("success") else 1
        else:
            from wobble.web.manager import run_web_build
            res = run_web_build(Path.cwd())
            return 0 if res.get("success") else 1

    elif cmd == "dev":
        from wobble.web.manager import run_web_dev
        return run_web_dev(Path.cwd(), port=args.port, host=_resolve_host(args))

    elif cmd == "preview":
        from wobble.web.manager import run_web_preview
        run_web_preview(Path.cwd(), port=args.port, host=_resolve_host(args))
        return 0

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
