"""
Wobble Unified CLI Dispatcher
Entry point for all 'wob' subcommands, options, and structured JSON outputs.
"""

import sys
import os
import time
import difflib
import argparse
from pathlib import Path
from typing import List, Optional

from wobble import __version__
from wobble.core.logger import Logger, set_logger, get_logger

# NOTE: heavyweight subcommand modules (doctor, apk, web, deps, plugins) are
# imported lazily inside their handlers. This keeps 'wob --version' and other
# trivial commands fast on mobile CPUs where import time is noticeable.


def build_parser() -> argparse.ArgumentParser:
    """Construct the main argument parser for Wobble CLI."""
    parser = argparse.ArgumentParser(
        prog="wob",
        description="⚡ Wobble - Production-Ready Termux Development Harness",
        epilog="""examples:
  wob doctor                        check the environment before building
  wob create android myapp          scaffold a native Android project
  wob create web site -f react      scaffold a React web project
  wob apk build && wob apk install  build and install a debug APK
  wob web preview                   serve a project on localhost & LAN
  wob --json project list           machine-readable output for scripts

Turn Termux into a unified Android & Web development workstation.""",
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
    p_web_dev.add_argument("--host", default="0.0.0.0", help="Host address to bind")
    sp_web.add_parser("build", help="Build web application for distribution")
    sp_web.add_parser("test", help="Run web test suite")
    p_web_prev = sp_web.add_parser("preview", help="Start preview server with localhost and LAN IP")
    p_web_prev.add_argument("-p", "--port", type=int, help="Port to serve on")
    p_web_prev.add_argument("--dir", help="Directory to serve")
    p_web_serve = sp_web.add_parser("serve", help="Static HTTP file server")
    p_web_serve.add_argument("-p", "--port", type=int, help="Port to serve on")

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
    subparsers.add_parser("doctor", help="Run comprehensive environment health diagnostics")

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

    # 11. wob update
    subparsers.add_parser("update", help="Check for Wobble updates")

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

    p_prev = subparsers.add_parser("preview", help="Preview current project locally and on LAN")
    p_prev.add_argument("-p", "--port", type=int, help="Port to listen on")

    return parser


def _suggest_names(unknown: str, candidates) -> str:
    """Return a friendly 'Did you mean ...?' hint for mistyped names."""
    matches = difflib.get_close_matches(unknown, list(candidates), n=3, cutoff=0.5)
    if matches:
        return f" Did you mean: {', '.join(matches)}?"
    return ""


def handle_create(args) -> int:
    from wobble.plugins.loader import get_plugin, list_plugins
    from wobble.project.manager import register_project

    logger = get_logger()
    p_type = args.type
    name = args.name

    # Guard against names that would escape the target directory or break tooling
    if name in (".", "..") or any(sep in name for sep in ("/", "\\")) or name.startswith("."):
        logger.error(f"Invalid project name '{name}'. Use a plain folder name without path separators.")
        return 1

    target_dir = Path(args.dir) if args.dir else (Path.cwd() / name)

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
                print("  wob web preview     # Preview on localhost & LAN")
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
                for p in projects:
                    reg_tag = "\033[2m[registered]\033[0m" if p["registered"] else ""
                    print(f"  ➜ \033[1m{p['name']:<18}\033[0m ({p['type']} / {p['framework']}) - {p['path']} {reg_tag}")
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
            for lim in report["limitations"]:
                print(f"  \033[1m● {lim['topic']}\033[0m")
                print(f"    Reality:  {lim['reality']}")
                print(f"    Solution: {lim['solution']}")
                print()
        return 0
    return 0


def handle_web(args) -> int:
    import time as _time
    from wobble.web.manager import run_web_dev, run_web_build, run_web_test, run_web_preview

    sub = args.subcommand or "preview"
    cwd = Path.cwd()

    if sub == "dev":
        return run_web_dev(cwd, port=args.port, host=args.host)
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
        run_web_preview(cwd, port=args.port, target_sub_dir=args.dir)
        return 0
    elif sub == "serve":
        run_web_preview(cwd, port=args.port)
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
                for a in apks:
                    size = f"{round(a.stat().st_size / (1024 * 1024), 2)} MB"
                    print(f"  ➜ \033[1m{a.name}\033[0m ({size}) - {a}")
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
            for p in plugins:
                cat = f"[{p.category}]"
                print(f"  ➜ \033[1m{p.name:<16}\033[0m {cat:<10} - {p.description}")
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
                targets.append(Path(dirpath) / d)
                dirnames.remove(d)  # don't descend into what we delete
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


_COMPLETION_BASH = """\
# Wobble (wob) bash completion — install with:
#   wob completion bash > ~/.local/share/bash-completion/completions/wob
# or:  source <(wob completion bash)
_wob_completions() {
    local cur prev cmds subcmds
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    cmds="create project android web apk deps doctor plugin config clean update schema completion build dev preview"

    if [ "$COMP_CWORD" -eq 1 ]; then
        COMPREPLY=( $(compgen -W "$cmds" -- "$cur") )
        return 0
    fi

    case "${COMP_WORDS[1]}" in
        create)   subcmds="android web" ;;
        project)  subcmds="list info open remove" ;;
        android)  subcmds="build clean info limitations" ;;
        web)      subcmds="dev build test preview serve" ;;
        apk)      subcmds="build list info install share sign clean" ;;
        deps)     subcmds="install add remove doctor list" ;;
        plugin)   subcmds="list info" ;;
        config)   subcmds="list get set" ;;
        completion) subcmds="bash zsh" ;;
        *)        subcmds="" ;;
    esac

    if [ "$COMP_CWORD" -eq 2 ] && [ -n "$subcmds" ]; then
        COMPREPLY=( $(compgen -W "$subcmds" -- "$cur") )
        return 0
    fi

    case "$prev" in
        -f|--framework) COMPREPLY=( $(compgen -W "vite react vue svelte nextjs python php static" -- "$cur") ) ;;
        --method)       COMPREPLY=( $(compgen -W "auto termux-open am adb" -- "$cur") ) ;;
        -m|--manager)   COMPREPLY=( $(compgen -W "auto termux npm pip composer" -- "$cur") ) ;;
        -p|--port|--host|--package|--dir|--dest|--keystore|--alias|--path|--release|--all|--yes)
                        COMPREPLY=( $(compgen -f -- "$cur") ) ;;
    esac
}
complete -F _wob_completions wob
"""

_COMPLETION_ZSH = """\
#compdef wob
# Wobble (wob) zsh completion — install with:
#   wob completion zsh > "${fpath[1]}/_wob"
_wob() {
    local -a cmds
    cmds=(
        'create:Create a new Android or Web project'
        'project:Manage and inspect projects'
        'android:Native Android development'
        'web:Web development workflows'
        'apk:Locate, inspect, build, and install APKs'
        'deps:Unified package and dependency management'
        'doctor:Run comprehensive environment health diagnostics'
        'plugin:List and inspect framework plugins'
        'config:Manage persistent user configuration'
        'clean:Clean temporary caches and build files'
        'update:Check for Wobble updates'
        'schema:Output machine-readable CLI schema'
        'completion:Generate shell completion script'
        'build:Intelligent build for current project'
        'dev:Start dev server for current project'
        'preview:Preview current project locally and on LAN'
    )
    if (( CURRENT == 2 )); then
        _describe 'command' cmds
        return
    fi
    case "${words[2]}" in
        create)   _values 'type' android web ;;
        project)  _values 'subcommand' list info open remove ;;
        android)  _values 'subcommand' build clean info limitations ;;
        web)      _values 'subcommand' dev build test preview serve ;;
        apk)      _values 'subcommand' build list info install share sign clean ;;
        deps)     _values 'subcommand' install add remove doctor list ;;
        plugin)   _values 'subcommand' list info ;;
        config)   _values 'subcommand' list get set ;;
        completion) _values 'shell' bash zsh ;;
    esac
}
_wob "$@"
"""


def handle_completion(args) -> int:
    logger = get_logger()
    shell = getattr(args, "shell", "bash") or "bash"
    script = _COMPLETION_BASH if shell == "bash" else _COMPLETION_ZSH
    if logger.json_mode:
        logger.json_output({"shell": shell, "script": script})
    else:
        print(script)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Initialize Logger
    logger = Logger(json_mode=args.json, no_color=args.no_color)
    set_logger(logger)

    if not args.command:
        parser.print_help()
        if not logger.json_mode:
            print("\nNew here? Try:  wob doctor  →  wob create web demo  →  wob web preview")
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
        run_doctor(json_mode=args.json)
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

    elif cmd == "update":
        logger.info(f"Wobble is currently at latest version v{__version__}.")
        return 0

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
        return run_web_dev(Path.cwd(), port=args.port)

    elif cmd == "preview":
        from wobble.web.manager import run_web_preview
        run_web_preview(Path.cwd(), port=args.port)
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
