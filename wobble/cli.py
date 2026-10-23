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
    """Raise parse errors so ``main`` can honor JSON mode and return exit 2.

    Help is rendered by :func:`_render_help`: a short, grouped layout instead of
    argparse's wall of ``{a,b,c,...}`` choices and long option dumps.
    """

    def error(self, message: str):
        raise UsageError(
            message,
            hint=f"Run '{self.prog} --help' for usage.",
            details={"usage": self.format_usage().strip()},
        )

    def format_help(self) -> str:
        try:
            return _render_help(self)
        except Exception:  # never let a help layout bug hide the command
            return super().format_help()


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


# ---------------------------------------------------------------------------
# Help layout
#
# Commands stay exactly as they are; this only decides how they are grouped
# when the user asks for help. A category (self, web, apk, ...) lists its
# commands, so `wob self` reads like a section of the manual rather than one
# opaque command.
# ---------------------------------------------------------------------------
_ROOT_GROUPS = (
    ("Projects", ("create", "project", "plugin")),
    ("Current project", ("dev", "build", "preview")),
    ("Android", ("android", "apk")),
    ("Web", ("web",)),
    ("Packages", ("deps",)),
    ("System", ("doctor", "config", "clean")),
    ("Wobble", ("self", "install", "uninstall", "rescue", "update")),
    ("Info", ("about", "schema", "completion", "version", "banner", "help")),
)

_SUBCOMMAND_GROUPS = {
    "project": (("Manage", ("list", "info", "open", "remove")),),
    "android": (("Build", ("build", "clean")), ("Inspect", ("info", "limitations"))),
    "web": (("Run", ("dev", "preview", "serve")), ("Ship", ("build", "test"))),
    "apk": (
        ("Build", ("build", "clean")),
        ("Inspect", ("list", "info", "sign")),
        ("Device", ("install", "share")),
    ),
    "deps": (("Packages", ("install", "add", "remove")), ("Inspect", ("doctor", "list"))),
    "plugin": (("Browse", ("list", "info")),),
    "config": (("Settings", ("list", "get", "set")),),
    "self": (
        ("Check", ("status", "health", "verify")),
        ("Repair", ("repair", "rescue")),
        ("Monitor", ("watch", "incidents")),
        ("Install", ("install", "uninstall")),
    ),
}

_ROOT_EXAMPLES = (
    "wob create web demo",
    "wob dev",
    "wob apk build",
    "wob doctor",
    "wob self status",
)


def _subparsers_action(parser: argparse.ArgumentParser):
    return next((action for action in parser._actions
                 if isinstance(action, argparse._SubParsersAction)), None)


def _decorate_help_tree(parser: argparse.ArgumentParser, prefix: str = "wob",
                        depth: int = 0) -> None:
    """Attach summaries, groups and correct ``prog`` names to the tree."""
    action = _subparsers_action(parser)
    if not action:
        return
    summaries = {choice.dest: (choice.help or "") for choice in action._choices_actions}
    for name, child in action.choices.items():
        child.prog = f"{prefix} {name}"
        child._wob_summary = summaries.get(name) or getattr(child, "_wob_summary", "")
        if depth == 0:
            child._wob_groups = _SUBCOMMAND_GROUPS.get(name)
        _decorate_help_tree(child, child.prog, depth + 1)


def _action_label(action: argparse.Action) -> str:
    if action.option_strings:
        label = ", ".join(action.option_strings)
        if action.nargs != 0 and not isinstance(
                action, (argparse._StoreTrueAction, argparse._StoreFalseAction)):
            label += " " + (action.metavar or action.dest.upper())
        return label
    label = action.metavar or action.dest
    if getattr(action, "choices", None):
        label += " {" + ",".join(str(choice) for choice in action.choices) + "}"
    return label


def _action_help(action: argparse.Action) -> str:
    text = action.help or ""
    if text in (argparse.SUPPRESS, "==SUPPRESS=="):
        return ""
    default = getattr(action, "default", None)
    is_toggle = isinstance(action, (argparse._StoreTrueAction, argparse._StoreFalseAction))
    if (not is_toggle and default not in (None, False, argparse.SUPPRESS)
            and "default" not in text.lower() and action.option_strings):
        text = f"{text} (default: {default})".strip()
    return text


def _help_rows(rows, width: int, indent: int = 2) -> List[str]:
    import textwrap

    if not rows:
        return []
    gap = 2
    left = max(len(label) for label, _ in rows) + gap
    out = []
    for label, text in rows:
        prefix = " " * indent + label.ljust(left)
        wrapped = textwrap.wrap(text, width=max(24, width - indent - left)) if text else [""]
        if not wrapped:
            wrapped = [""]
        out.append((prefix + wrapped[0]).rstrip())
        for extra in wrapped[1:]:
            out.append((" " * (indent + left) + extra).rstrip())
    return out


def _render_help(parser: argparse.ArgumentParser) -> str:
    import shutil

    width = min(max(shutil.get_terminal_size((80, 24)).columns, 60), 100)
    groups = getattr(parser, "_wob_groups", None)
    summary = getattr(parser, "_wob_summary", "")
    action = _subparsers_action(parser)
    choices = {choice.dest: (choice.help or "") for choice in action._choices_actions} if action else {}

    out: List[str] = []
    if parser.prog == "wob":
        out.append(f"Wobble {__version__}")
    else:
        out.append(parser.prog)
    if summary:
        out.append(summary)

    out.append("")
    out.append("Usage")
    if groups:
        out.append(f"  {parser.prog} <command> [options]")
    else:
        usage = parser.format_usage().strip()
        usage = usage[len("usage:"):].strip() if usage.startswith("usage:") else usage
        out.extend("  " + line.strip() for line in usage.splitlines())

    if groups:
        listed = set()
        for title, names in groups:
            rows = [(name, choices.get(name, "")) for name in names if name in choices]
            if not rows:
                continue
            listed.update(name for name, _ in rows)
            out.append("")
            out.append(title)
            out.extend(_help_rows(rows, width))
        leftover = [(name, text) for name, text in choices.items() if name not in listed]
        if leftover:
            out.append("")
            out.append("More")
            out.extend(_help_rows(leftover, width))

    positionals = [a for a in parser._actions
                   if not a.option_strings and a.dest not in ("help",)]
    if positionals and not groups:
        out.append("")
        out.append("Arguments")
        out.extend(_help_rows([(_action_label(a), _action_help(a)) for a in positionals], width))

    optionals = [a for a in parser._actions if a.option_strings and a.dest != "help"]
    out.append("")
    out.append("Options")
    out.extend(_help_rows([(_action_label(a), _action_help(a)) for a in optionals]
                          + [("-h, --help", "Show this help")], width))

    if parser.prog == "wob":
        out.append("")
        out.append("Examples")
        out.extend("  " + example for example in _ROOT_EXAMPLES)

    out.append("")
    if groups:
        out.append(f"Run '{parser.prog} <command> --help' for command options.")
    return "\n".join(out)


def _resolve_help_target(parser: argparse.ArgumentParser, topics):
    target = parser
    for topic in topics:
        action = _subparsers_action(target)
        if not action or topic not in action.choices:
            return None
        target = action.choices[topic]
    return target


def _show_help(parser: argparse.ArgumentParser, topics=()) -> int:
    """Print help for the root, a category, or a single command."""
    logger = get_logger()
    target = _resolve_help_target(parser, topics)
    if target is None:
        logger.error(f"Unknown command: {' '.join(topics)}")
        logger.hint("Run 'wob --help' to see all commands.")
        return 1
    if logger.json_mode:
        action = _subparsers_action(target)
        usage = target.usage or target.format_usage().strip()
        if usage.startswith("usage:"):
            usage = usage[len("usage:"):].strip()
        payload = {
            "command": target.prog,
            "summary": getattr(target, "_wob_summary", ""),
            "usage": usage,
        }
        if action:
            payload["subcommands"] = [
                {"name": choice.dest, "description": choice.help} for choice in action._choices_actions
            ]
        logger.json_output(payload)
        return 0
    print(target.format_help(), end="")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Construct the main argument parser for Wobble CLI."""
    parser = WobbleArgumentParser(
        prog="wob",
        usage="wob <command> [options]",
        description="Android and web development from Termux.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser._wob_summary = "Android and web development from Termux."
    parser._wob_groups = _ROOT_GROUPS

    parser.add_argument("--version", action="version", version=f"Wobble v{__version__}",
                        help="Print the version and exit")
    parser.add_argument("--json", action="store_true",
                        help="Print JSON for scripts and agents")
    parser.add_argument("--no-color", action="store_true", help="Disable colour")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Show tracebacks for unexpected errors")

    subparsers = parser.add_subparsers(dest="command", metavar="<command>")

    # -- projects ----------------------------------------------------------
    p_create = subparsers.add_parser(
        "create", help="Create an Android or web project",
        usage="wob create <android|web> <name> [options]")
    p_create.add_argument("type", choices=["android", "web"],
                          help="Project type")
    p_create.add_argument("name", help="Project name and directory")
    p_create.add_argument("-f", "--framework", default="auto",
                          help="Template: vite, react, vue, svelte, nextjs, "
                               "python, php, static")
    p_create.add_argument("-p", "--package",
                          help="Android package ID (e.g. com.example.myapp)")
    p_create.add_argument("-d", "--dir",
                          help="Destination directory (default: ./<name>)")

    p_project = subparsers.add_parser(
        "project", help="Manage your projects", usage="wob project <command> [options]")
    sp_project = p_project.add_subparsers(dest="subcommand", metavar="<command>")
    p_proj_list = sp_project.add_parser("list", help="List known projects")
    p_proj_list.add_argument("--path", help="Directory to scan (default: current)")
    p_proj_info = sp_project.add_parser("info", help="Show project details")
    p_proj_info.add_argument("--path", help="Project root (default: current)")
    p_proj_open = sp_project.add_parser("open", help="Show a project's commands")
    p_proj_open.add_argument("name", help="Project name or directory")
    p_proj_rm = sp_project.add_parser("remove", help="Unregister a project")
    p_proj_rm.add_argument("name", help="Project name")

    # -- android -----------------------------------------------------------
    p_android = subparsers.add_parser(
        "android", help="Native Android projects", usage="wob android <command> [options]")
    sp_android = p_android.add_subparsers(dest="subcommand", metavar="<command>")
    p_and_build = sp_android.add_parser("build", help="Compile the project with Gradle")
    p_and_build.add_argument("--release", action="store_true", help="Build a release APK")
    p_and_build.add_argument("--clean", action="store_true", help="Clean before building")
    sp_android.add_parser("clean", help="Remove Gradle build output")
    sp_android.add_parser("info", help="Show the Android project")
    sp_android.add_parser("limitations", help="Explain Termux and Android limits")

    # -- web ---------------------------------------------------------------
    p_web = subparsers.add_parser(
        "web", help="Web development", usage="wob web <command> [options]")
    sp_web = p_web.add_subparsers(dest="subcommand", metavar="<command>")
    p_web_dev = sp_web.add_parser("dev", help="Start the framework dev server")
    p_web_dev.add_argument("-p", "--port", type=_port_number, help="Port (1-65535)")
    p_web_dev.add_argument("--host", default=None, help="Host to bind (default: 127.0.0.1)")
    p_web_dev.add_argument("--lan", action="store_true",
                           help="Listen on all interfaces (0.0.0.0)")
    sp_web.add_parser("build", help="Build for production")
    sp_web.add_parser("test", help="Run the test suite")
    p_web_prev = sp_web.add_parser("preview", help="Serve the built site")
    p_web_prev.add_argument("-p", "--port", type=_port_number, help="Port (1-65535)")
    p_web_prev.add_argument("--dir", help="Directory to serve")
    p_web_prev.add_argument("--host", default=None, help="Host to bind (default: 127.0.0.1)")
    p_web_prev.add_argument("--lan", action="store_true",
                            help="Listen on all interfaces (0.0.0.0)")
    p_web_serve = sp_web.add_parser("serve", help="Serve a static directory")
    p_web_serve.add_argument("-p", "--port", type=_port_number, help="Port (1-65535)")
    p_web_serve.add_argument("--host", default=None, help="Host to bind (default: 127.0.0.1)")
    p_web_serve.add_argument("--lan", action="store_true",
                             help="Listen on all interfaces (0.0.0.0)")

    # -- apk ---------------------------------------------------------------
    p_apk = subparsers.add_parser(
        "apk", help="Build and manage APKs", usage="wob apk <command> [options]")
    sp_apk = p_apk.add_subparsers(dest="subcommand", metavar="<command>")
    p_apk_build = sp_apk.add_parser("build", help="Build and locate an APK")
    p_apk_build.add_argument("--release", action="store_true", help="Build a release APK")
    p_apk_list = sp_apk.add_parser("list", help="Find built APKs")
    p_apk_list.add_argument("--path", help="Directory to scan (default: current)")
    p_apk_info = sp_apk.add_parser("info", help="Inspect an APK")
    p_apk_info.add_argument("file", nargs="?", help="APK path (default: newest)")
    p_apk_inst = sp_apk.add_parser("install", help="Install on this device")
    p_apk_inst.add_argument("file", nargs="?", help="APK path (default: newest)")
    p_apk_inst.add_argument("--method", choices=["auto", "termux-open", "am", "adb"],
                            default="auto", help="Installer to use")
    p_apk_share = sp_apk.add_parser("share", help="Copy to Downloads")
    p_apk_share.add_argument("file", nargs="?", help="APK path (default: newest)")
    p_apk_share.add_argument("--dest",
                             help="Destination folder (default: ~/storage/shared/Download)")
    p_apk_sign = sp_apk.add_parser("sign", help="Sign with apksigner")
    p_apk_sign.add_argument("file", nargs="?", help="APK path (default: newest)")
    p_apk_sign.add_argument("--keystore", help="Keystore file")
    p_apk_sign.add_argument("--alias", help="Key alias")
    sp_apk.add_parser("clean", help="Remove built APKs")

    # -- deps --------------------------------------------------------------
    p_deps = subparsers.add_parser(
        "deps", help="Install dependencies and toolchains",
        usage="wob deps <command> [options]")
    sp_deps = p_deps.add_subparsers(dest="subcommand", metavar="<command>")
    p_deps_inst = sp_deps.add_parser("install", help="Install for a stack or project")
    p_deps_inst.add_argument("target", nargs="?",
                             help="Stack: android, node, python or php (default: project)")
    p_deps_add = sp_deps.add_parser("add", help="Add a package")
    p_deps_add.add_argument("package", help="Package name")
    p_deps_add.add_argument("-m", "--manager",
                            choices=["auto", "termux", "npm", "pip", "composer"],
                            default="auto", help="Package manager")
    p_deps_rm = sp_deps.add_parser("remove", help="Remove a package")
    p_deps_rm.add_argument("package", help="Package name")
    p_deps_rm.add_argument("-m", "--manager",
                           choices=["auto", "termux", "npm", "pip", "composer"],
                           default="auto", help="Package manager")
    sp_deps.add_parser("doctor", help="Check dependency health")
    sp_deps.add_parser("list", help="List project dependencies")

    # -- doctor ------------------------------------------------------------
    p_doctor = subparsers.add_parser(
        "doctor", help="Check Termux and the toolchain",
        usage="wob doctor [options]")
    p_doctor.add_argument("--quick", action="store_true",
                          help="Skip version probes (PATH lookups only)")
    p_doctor.add_argument("--only", metavar="CATEGORIES",
                          help="Limit to system, resources, environment, tools, "
                               "web, android or wobble")
    p_doctor.add_argument("--strict", action="store_true",
                          help="Exit 1 when anything warns or fails")
    p_doctor.add_argument("--fail-on", choices=["never", "warning", "missing", "error"],
                          default="never", metavar="LEVEL",
                          help="Exit 1 at or above this severity")
    p_doctor.add_argument("--timings", action="store_true", help="Show timings")
    p_doctor.add_argument("--no-cache", action="store_true", help="Ignore the probe cache")
    p_doctor.add_argument("--save-baseline", action="store_true",
                          help="Save this run as the baseline")
    p_doctor.add_argument("--no-save", action="store_true", help="Do not save a baseline")

    # -- plugin ------------------------------------------------------------
    p_plugin = subparsers.add_parser(
        "plugin", help="Browse framework templates",
        usage="wob plugin <command> [options]")
    sp_plugin = p_plugin.add_subparsers(dest="subcommand", metavar="<command>")
    sp_plugin.add_parser("list", help="List frameworks")
    p_plug_info = sp_plugin.add_parser("info", help="Show framework details")
    p_plug_info.add_argument("name", help="Framework name")

    # -- config ------------------------------------------------------------
    p_config = subparsers.add_parser(
        "config", help="Read and write settings",
        usage="wob config <command> [options]")
    sp_config = p_config.add_subparsers(dest="subcommand", metavar="<command>")
    sp_config.add_parser("list", help="List settings")
    p_cfg_get = sp_config.add_parser("get", help="Read a setting")
    p_cfg_get.add_argument("key", help="Setting name")
    p_cfg_set = sp_config.add_parser("set", help="Change a setting")
    p_cfg_set.add_argument("key", help="Setting name")
    p_cfg_set.add_argument("value", help="New value")

    # -- clean -------------------------------------------------------------
    p_clean = subparsers.add_parser("clean", help="Remove build output")
    p_clean.add_argument("--all", action="store_true",
                         help="Also remove node_modules and caches")
    p_clean.add_argument("-y", "--yes", action="store_true",
                         help="Skip the confirmation prompt")

    # -- self --------------------------------------------------------------
    p_self = subparsers.add_parser(
        "self", help="Check, repair and maintain Wobble",
        usage="wob self <command> [options]")
    sp_self = p_self.add_subparsers(dest="subcommand", metavar="<command>")

    for name, help_text in (
        ("status", "Runtime, launcher and PATH health"),
        ("health", "Same as status"),
    ):
        p_self_status = sp_self.add_parser(name, help=help_text)
        p_self_status.add_argument("--deep", action="store_true",
                                   help="Hash every installed file")
        p_self_status.add_argument("--strict", action="store_true",
                                   help="Exit 1 on warnings too")
        p_self_status.add_argument("--brief", action="store_true",
                                   help="One-line summary")
        _add_target_args(p_self_status)

    p_self_verify = sp_self.add_parser("verify", help="Check installed files")
    p_self_verify.add_argument("--serial", action="store_true",
                               help="Hash sequentially (debugging)")
    p_self_verify.add_argument("--strict", action="store_true",
                               help="Also fail if the launcher is not executable")
    _add_target_args(p_self_verify)

    p_self_repair = sp_self.add_parser("repair", help="Restore damaged files")
    p_self_repair.add_argument("--compile", dest="compile", action="store_true", default=True,
                               help="Recompile missing bytecode (default)")
    p_self_repair.add_argument("--no-compile", dest="compile", action="store_false",
                               help="Skip bytecode compilation")
    p_self_repair.add_argument("--completions", dest="completions", action="store_true",
                               default=True, help="Regenerate shell completions (default)")
    p_self_repair.add_argument("--no-completions", dest="completions", action="store_false",
                               help="Skip shell completions")
    p_self_repair.add_argument("--config", dest="fix_config", action="store_true",
                               default=True, help="Back up corrupt config (default)")
    p_self_repair.add_argument("--no-config", dest="fix_config", action="store_false",
                               help="Leave config files alone")
    p_self_repair.add_argument("--path", action="store_true",
                               help="Add the launcher directory to PATH")
    p_self_repair.add_argument("--accept-current", action="store_true",
                               help="Re-baseline hashes after a local patch")
    p_self_repair.add_argument("-y", "--yes", action="store_true",
                               help="Do not ask for confirmation with --accept-current")
    _add_repair_recovery_args(p_self_repair)
    _add_target_args(p_self_repair)

    p_self_rescue = sp_self.add_parser("rescue", help="Rebuild from the snapshot")
    p_self_rescue.add_argument("--dry-run", action="store_true",
                               help="Show the plan without changing anything")
    _add_repair_recovery_args(p_self_rescue, simple=True)
    _add_target_args(p_self_rescue)

    p_self_watch = sp_self.add_parser("watch", help="Watch health live")
    p_self_watch.add_argument("--interval", type=float, default=2.0, metavar="SECONDS",
                              help="Seconds between checks (default: 2)")
    p_self_watch.add_argument("--count", type=int, default=0, metavar="N",
                              help="Stop after N checks (default: run until Ctrl+C)")
    p_self_watch.add_argument("--deep", action="store_true",
                              help="Hash files on every tick (slow)")
    _add_target_args(p_self_watch)

    p_self_incidents = sp_self.add_parser("incidents", help="Show the failure log")
    p_self_incidents.add_argument("--limit", type=int, default=10, metavar="N",
                                  help="Show at most N incidents (default: 10)")
    p_self_incidents.add_argument("--clear", action="store_true",
                                  help="Delete the log after showing it")

    p_self_install = sp_self.add_parser("install", help="Install a standalone copy")
    _add_install_args(p_self_install)
    p_self_uninstall = sp_self.add_parser("uninstall", help="Remove the installation")
    _add_uninstall_args(p_self_uninstall)

    # Top-level aliases: same actions, easier to discover.
    p_install = subparsers.add_parser("install", help="Install Wobble as software")
    _add_install_args(p_install)
    p_uninstall = subparsers.add_parser("uninstall", help="Remove the installation")
    _add_uninstall_args(p_uninstall)
    p_rescue = subparsers.add_parser("rescue", help="Emergency recovery")
    p_rescue.add_argument("--dry-run", action="store_true",
                          help="Show the plan without changing anything")
    _add_repair_recovery_args(p_rescue, simple=True)
    _add_target_args(p_rescue)

    # -- info and tools ----------------------------------------------------
    subparsers.add_parser("update", help="Check for updates")
    subparsers.add_parser("version", help="Print the version")
    p_help = subparsers.add_parser("help", help="Show help")
    p_help.add_argument("topic", nargs="*", metavar="command",
                        help="Command to describe (e.g. self status)")
    subparsers.add_parser("banner", help="Print the wordmark")
    subparsers.add_parser("about", help="Show version and environment")
    subparsers.add_parser("schema", help="Print the CLI schema (JSON)")
    p_compl = subparsers.add_parser("completion", help="Generate shell completion")
    p_compl.add_argument("shell", nargs="?", default="bash", choices=["bash", "zsh"],
                         help="Shell to generate a script for (default: bash)")

    # -- shortcuts ---------------------------------------------------------
    p_build = subparsers.add_parser("build", help="Build the current project")
    p_build.add_argument("--release", action="store_true",
                         help="Build a release APK or production bundle")

    p_dev = subparsers.add_parser("dev", help="Run the current project")
    p_dev.add_argument("-p", "--port", type=_port_number, help="Port (1-65535)")
    p_dev.add_argument("--host", default=None, help="Host to bind (default: 127.0.0.1)")
    p_dev.add_argument("--lan", action="store_true",
                       help="Listen on all interfaces (0.0.0.0)")

    p_prev = subparsers.add_parser("preview", help="Preview the current project")
    p_prev.add_argument("-p", "--port", type=_port_number, help="Port (1-65535)")
    p_prev.add_argument("--host", default=None, help="Host to bind (default: 127.0.0.1)")
    p_prev.add_argument("--lan", action="store_true",
                        help="Listen on all interfaces (0.0.0.0)")

    _decorate_help_tree(parser, parser.prog)
    return parser


def _add_repair_recovery_args(parser: argparse.ArgumentParser, simple: bool = False) -> None:
    """Flags controlling how ``repair``/``rescue`` restore the runtime."""
    if not simple:
        parser.add_argument("--restore", dest="restore", action="store_true", default=True,
                            help="Restore missing or corrupted runtime files (default)")
        parser.add_argument("--no-restore", dest="restore", action="store_false",
                            help="Only fix launchers/bytecode/config; never rewrite runtime files")
        parser.add_argument("--dry-run", action="store_true",
                            help="Show the recovery plan without changing anything")
    parser.add_argument("--from", dest="recovery_source", default="auto",
                        choices=["auto", "snapshot", "source", "network"],
                        help="Recovery source to prefer (default: auto)")
    parser.add_argument("--url", help="Release archive URL for --from network")
    parser.add_argument("--network", action="store_true",
                        help="Allow downloading a release archive when nothing local works")
    parser.add_argument("--emergency", action="store_true",
                        help="Full recovery: allow downloads and accept a version change")
    parser.add_argument("--snapshot", action="store_true",
                        help="Rewrite the offline recovery snapshot from the current runtime")
    parser.add_argument("--no-backup", action="store_true",
                        help="Do not keep copies of the damaged files")


def _add_install_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", help="Install directory (default: ~/.local/share/wobble)")
    parser.add_argument("--bin", help="Directory for the 'wob' launcher (default: ~/.local/bin)")
    parser.add_argument("--force", action="store_true", help="Replace an existing foreign 'wob' executable")
    parser.add_argument("--no-completion", action="store_true", help="Do not install shell completions")
    parser.add_argument("--no-path", action="store_true", help="Do not edit ~/.bashrc / ~/.zshrc")
    parser.add_argument("--no-snapshot", action="store_true",
                        help="Skip the offline recovery snapshot (saves disk, loses offline repair)")


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
    logger.detail("framework", plugin.name)
    logger.detail("location", str(target_dir))

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
            logger.success(f"Project '{name}' created")
            print()
            print("Next")
            print(f"  cd {target_dir}")
            if p_type == "android":
                print("  wob apk build")
                print("  wob apk install")
            else:
                print("  wob deps install")
                print("  wob web dev")
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
            logger.heading("Projects")
            if not projects:
                print("  none yet. Create one with: wob create web <name>")
            else:
                from wobble.core import theme
                for p in projects:
                    name = theme.paint(f"{p['name']:<18}", theme.BOLD, enabled=logger.use_color)
                    kind = f"{p['type']}/{p['framework']}"
                    tag = theme.paint("  registered", theme.DIM, enabled=logger.use_color) if p["registered"] else ""
                    print(f"  {name} {kind:<16} {p['path']}{tag}")
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
            logger.detail("type", info.get("type"))
            logger.detail("framework", info.get("framework"))
            logger.detail("version", info.get("version"))
            if info.get("package_id"):
                logger.detail("package id", info.get("package_id"))
            logger.detail("location", str(target.resolve()))
            metrics = info.get("metrics", {})
            logger.detail("files", f"{metrics.get('file_count', 0)} files ({metrics.get('total_size_human', '')})")
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
            logger.detail("path", p["path"])
            logger.detail("type", f"{p['type']} ({p['framework']})")
            print()
            print("Commands")
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
            logger.detail("build time", f"{res['elapsed_seconds']}s")
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
                logger.detail("name", spec.name)
                logger.detail("package id", spec.package_id)
            logger.detail("apks found", len(apks))
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
                topic = theme.paint(lim["topic"], theme.BOLD, enabled=logger.use_color)
                print(f"  {topic}")
                print(f"    now  {lim['reality']}")
                print(f"    fix  {lim['solution']}")
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
            get_logger().detail("build time", f"{res['elapsed_seconds']}s")
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
            logger.detail("build time", f"{res['elapsed_seconds']}s")
        return 0 if res.get("success") else 1

    elif sub == "list":
        scan_dir = Path(args.path) if hasattr(args, "path") and args.path else cwd
        apks = find_apks(scan_dir)
        if logger.json_mode:
            logger.json_output({"apks": [str(a) for a in apks], "count": len(apks)})
        else:
            logger.heading("APKs")
            if not apks:
                print("  none yet. Build one with: wob apk build")
            else:
                from wobble.core import theme
                for a in apks:
                    size = f"{round(a.stat().st_size / (1024 * 1024), 2)} MB"
                    name = theme.paint(f"{a.name:<28}", theme.BOLD, enabled=logger.use_color)
                    print(f"  {name} {size:>9}  {a}")
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
            logger.detail("package", info.get("package_name"))
            logger.detail("label", info.get("app_label"))
            logger.detail("version", f"{info.get('version_name')} (Code: {info.get('version_code')})")
            logger.detail("sdk", f"Min: {info.get('min_sdk')} | Target: {info.get('target_sdk')}")
            logger.detail("size", info.get("size_human"))
            logger.detail("sha256", info.get("sha256"))
            logger.detail("abis", ", ".join(info.get("native_abis", [])))
            perms = info.get("permissions", [])
            if perms:
                logger.detail("permissions", f"{len(perms)} declared ({', '.join(perms[:3])}...)")
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
                logger.detail("destination", res.get("destination"))
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
                logger.detail("keystore", res.get("keystore"))
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
            get_logger().heading(f"Dependencies: {res['project']}")
            if res["status"] == "ok":
                get_logger().success("all dependencies look healthy")
            else:
                for issue in res["issues"]:
                    get_logger().warn(issue["message"])
                    print(f"        fix  {issue['fix']}")
            print()
        return 0

    elif sub == "list":
        res = deps_list(cwd)
        if get_logger().json_mode:
            get_logger().json_output(res)
        else:
            get_logger().heading(f"Dependencies: {res['project']}")
            if res.get("dependencies"):
                print("  Packages")
                for k, v in res["dependencies"].items():
                    print(f"    {k:<24} {v}")
            if res.get("dev_dependencies"):
                print("  Dev packages")
                for k, v in res["dev_dependencies"].items():
                    print(f"    {k:<24} {v}")
            if res.get("system"):
                print("  System")
                for pkg in res["system"]:
                    print(f"    {pkg}")
            if not any(res.get(k) for k in ("dependencies", "dev_dependencies", "system")):
                print("  none declared")
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
            logger.heading("Frameworks")
            from wobble.core import theme
            for p in plugins:
                name = theme.paint(f"{p.name:<12}", theme.BOLD, enabled=logger.use_color)
                cat = theme.paint(f"{p.category:<8}", theme.DIM, enabled=logger.use_color)
                print(f"  {name} {cat} {p.description}")
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
            logger.detail("version", p.version)
            logger.detail("category", p.category)
            logger.detail("description", p.description)
            logger.detail("tools", ", ".join(p.required_tools) if p.required_tools else "none")
            logger.detail("packages", ", ".join(p.required_system_packages) if p.required_system_packages else "none")
            prereq = p.check_prerequisites()
            logger.detail("ready", "yes" if prereq["ready"] else f"Missing: {prereq['missing_tools']}")
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
            logger.heading("Settings")
            for k, v in cfg.all().items():
                print(f"  {k:<26} {v}")
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
    print(theme.rule(f"About Wobble v{__version__}", width=70, use_color=logger.use_color))
    for row in rows:
        print("  " + row)
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
        print(f"{theme.badge(overall, logger.use_color).rstrip()}  "
              f"{report['status']}  {report['mode']} v{report['version']}  "
              f"{counts['ok']} ok  {counts['warning']} warnings  "
              f"{counts['critical']} critical  ({report['elapsed_ms']} ms)")
        return code

    print(selfcheck.render(report, use_color=logger.use_color))
    if report["mode"] == "legacy-symlink":
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

    print(theme.rule("Installation", width=66, use_color=logger.use_color))
    if data.get("error"):
        logger.status("warning", "manifest", data["error"])
        logger.hint(data.get("hint") or "Install Wobble with: sh install.sh")
        print()
        return 1

    logger.status("ok" if data.get("ok") else "error", "manifest",
                  f"{data.get('checked', 0)}/{data.get('file_count', 0)} files verified "
                  f"in {data.get('elapsed_ms', 0)} ms")
    logger.detail("hashed", _human_bytes(data.get("hashed_bytes", 0)))
    logger.detail("parallel", "yes" if data.get("parallel") else "no (small tree)")
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
        logger.hint("Restore the damaged files from the verified snapshot: wob self repair")
        logger.hint("If no snapshot/source is available: wob self repair --emergency")
        logger.hint("If you patched the install on purpose: wob self repair --accept-current")
    print()
    return 0 if data.get("ok") else 1


def _self_repair(args, emergency: bool = False, title: str = "Repair") -> int:
    from wobble.core import selfcheck, theme

    logger = get_logger()
    root, bin_dir = _self_targets(args)
    accept_current = bool(getattr(args, "accept_current", False))
    assume_yes = bool(getattr(args, "yes", False))
    is_emergency = bool(emergency or getattr(args, "emergency", False))
    dry_run = bool(getattr(args, "dry_run", False))

    if accept_current and not assume_yes and not dry_run:
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
        restore=bool(getattr(args, "restore", True)),
        source=getattr(args, "recovery_source", "auto") or "auto",
        network=bool(getattr(args, "network", False)),
        url=getattr(args, "url", None),
        dry_run=dry_run,
        emergency=is_emergency,
        refresh_snapshot=bool(getattr(args, "snapshot", False)),
        backup=not bool(getattr(args, "no_backup", False)),
    )

    if logger.json_mode:
        logger.json_output(data)
        return 0 if data.get("success") else 1

    print(theme.rule(title, width=66, use_color=logger.use_color))
    if data.get("error") and not data.get("actions"):
        logger.error(data["error"])
        if data.get("fix") or data.get("hint"):
            logger.hint(data.get("fix") or data.get("hint"))
        print()
        return 1

    restore_info = data.get("restore") or {}
    if dry_run:
        plan = data.get("plan") or {}
        logger.status("info", "dry run", "no files were changed")
        if plan.get("restore"):
            logger.status("warning", "would restore", f"{len(plan['restore'])} file(s)")
            for rel in plan["restore"][:10]:
                logger.detail("file", rel)
        elif restore_info.get("mode") == "full":
            logger.status("warning", "would reinstall",
                          f"from {(plan.get('reinstall_from') or {}).get('kind', 'source')}")
        else:
            logger.status("ok", "runtime", "nothing to restore")
        source = (plan.get("source") or restore_info.get("source") or {})
        if source:
            logger.detail("source", f"{source.get('kind')} ({source.get('path')})")
        print()
        return 0 if data.get("success") else 1

    if not data.get("actions"):
        logger.info("Nothing needed repair.")
    for action in data.get("actions", []):
        name = action.get("action")
        if name == "restore_runtime":
            source = action.get("source") or {}
            count = len(action.get("restored") or [])
            if action.get("mode") == "full":
                logger.status("ok", "runtime", "reinstalled from "
                              f"{source.get('kind') or 'source'}")
            else:
                logger.status("ok", "runtime", f"restored {count} file(s) from "
                              f"{source.get('kind') or 'source'}")
            if action.get("missing") or action.get("modified"):
                logger.detail("damaged", f"{len(action.get('modified') or [])} modified, "
                                         f"{len(action.get('missing') or [])} missing")
            if action.get("backup_dir"):
                logger.detail("backup", action["backup_dir"])
        elif name == "backup_corrupt_manifest":
            logger.status("warning", "corrupt manifest",
                          f"kept at {action.get('backup')}")
        elif name == "rebuild_manifest":
            logger.status("warning", "manifest",
                          f"rebuilt from disk ({action.get('file_count', 0)} files)")
        elif name == "create_snapshot":
            logger.status("ok", "snapshot",
                          f"v{action.get('version')}  {action.get('file_count', 0)} files")
        elif name == "write_rescue_assets":
            logger.status("ok", "rescue", action.get("rescue_sh") or "installed")
        elif name == "prune_backups":
            logger.detail("backups", f"pruned {len(action.get('removed', []))}")
        elif name == "rewrite_launchers":
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
    for warning in data.get("warnings", []):
        logger.warn(f"{warning.get('action')}: {warning.get('warning') or warning.get('error')}")
    for failure in data.get("failed", []):
        logger.error(f"{failure.get('action')}: {failure.get('error')}")
    for problem in data.get("unresolved", []):
        logger.warn(f"{problem['problem']} -> {problem['fix']}")
    if data.get("success"):
        restored = ((data.get("restore") or {}).get("restored") or [])
        if restored:
            logger.success("Installation restored and verified.")
        else:
            logger.success("Installation repaired and verified.")
    else:
        logger.error(data.get("error") or "Repair could not complete.")
        if data.get("hint"):
            logger.hint(data["hint"])
    print()
    return 0 if data.get("success") else 1


def _self_rescue(args) -> int:
    """Emergency recovery: always attempt a restore, allow downloads."""
    logger = get_logger()
    if not logger.json_mode:
        logger.warn("Emergency recovery: restoring the runtime from the best available source.")
    return _self_repair(args, emergency=True, title="Rescue")


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
        print(f"watching installation health every {interval:g}s "
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
                    print(f"{stamp}  {change['change']:<9} {change['code']}  "
                          f"{before} -> {after}", flush=True)
                if any(change["change"] in ("new", "worsened") and change["to"] == "critical"
                       for change in changes):
                    print(f"{stamp}  fix       run: wob self repair", flush=True)
            else:
                print(f"{stamp}  {report['status']}  "
                      f"{report['counts']['ok']} ok  "
                      f"{report['counts']['warning']} warnings  "
                      f"{report['counts']['critical']} critical  "
                      f"({report['elapsed_ms']} ms)", flush=True)
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

    print(theme.rule("Failure log", width=66, use_color=logger.use_color))
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
    if sub == "rescue":
        return _self_rescue(args)
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
            snapshot=not getattr(args, "no_snapshot", False),
        )
    except installer.InstallerError as exc:
        logger.error(str(exc))
        return 1

    if logger.json_mode:
        logger.json_output(data)
        return 0

    if not os.environ.get("WOBBLE_INSTALL_QUIET"):
        print()
    print(theme.rule("Installed", width=64, use_color=logger.use_color))
    logger.status("ok", "version", data["version"])
    logger.detail("app dir", data["app_dir"])
    logger.detail("launcher", data["launcher"])
    logger.detail("files", f"{data['file_count']} ({_human_bytes(data['total_bytes'])})")
    logger.detail("time", f"{data['elapsed_seconds']}s")
    if data.get("completions"):
        logger.detail("completions", ", ".join(data["completions"]))
    if data.get("shell_configs"):
        logger.detail("PATH", ", ".join(data["shell_configs"]))
    snapshot = data.get("snapshot") or {}
    if snapshot.get("ok"):
        logger.detail("snapshot", f"{snapshot.get('file_count', 0)} files -> {snapshot.get('app')}")
    elif not snapshot.get("skipped"):
        logger.warn("Offline recovery snapshot was not written: "
                    f"{snapshot.get('error') or 'unknown error'}")
    if data.get("rescue"):
        logger.detail("rescue", data["rescue"].get("rescue_sh") or "not installed")
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

    print(theme.rule("Uninstalled", width=64, use_color=logger.use_color))
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
    logger.heading("Updates")
    logger.detail("installed", f"v{__version__}")
    logger.detail("mode", info.get("mode"))
    print()
    print("To upgrade")
    print("  git pull && sh install.sh")
    logger.hint("Projects, registry, config and keystores are kept.")
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


#: Commands that only group other commands. Typing one on its own shows its
#: command list instead of silently running an unrelated default action.
CATEGORY_COMMANDS = ("project", "android", "web", "apk", "deps", "plugin", "config", "self")


def _dispatch(parser: argparse.ArgumentParser, args) -> int:
    """Route a parsed command to its handler. Heavy modules load only when needed."""
    logger = get_logger()
    cmd = args.command

    # A category without a subcommand is an incomplete command, not a default
    # action. Show its menu so `wob self` answers "what can self do?".
    if cmd in CATEGORY_COMMANDS and not getattr(args, "subcommand", None):
        return _show_help(parser, (cmd,))

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
        return _show_help(parser, getattr(args, "topic", None) or ())

    elif cmd == "update":
        return handle_update(args)

    elif cmd == "banner":
        return handle_banner(args)

    elif cmd == "about":
        return handle_about(args)

    elif cmd == "self":
        return handle_self(args)

    elif cmd == "rescue":
        return _self_rescue(args)

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
