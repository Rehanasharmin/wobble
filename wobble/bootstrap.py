"""
Wobble Fast Bootstrap
Handles the two most common invocations (``wob --version`` and bare ``wob``)
without importing argparse, difflib, or any subcommand module.

``python -m wobble --version`` therefore completes in a fraction of the time a
full CLI parse would take — which matters on phones where every millisecond of
startup is visible.
"""

import json
import sys
from typing import List, Optional

from wobble import __version__


def _version_text() -> str:
    return f"Wobble v{__version__}"


def print_landing() -> None:
    """Render the quick-start landing screen (no argparse involved)."""
    from wobble.core import theme

    use_color = theme.color_enabled()
    print()
    print(theme.banner(use_color, theme.TAGLINE))
    print()
    print(theme.rule("quick start", width=64, use_color=use_color))
    rows = [
        ("wob doctor", "audit your Termux environment"),
        ("wob create web demo", "scaffold a web project"),
        ("wob create android app", "scaffold a native Android app"),
        ("wob dev", "start the dev server for this project"),
        ("wob preview --lan", "preview locally or on your Wi-Fi"),
        ("wob self status", "check how Wobble is installed"),
        ("wob --help", "list every command and flag"),
    ]
    for command, description in rows:
        cmd = theme.paint(command, theme.BRIGHT_CYAN, theme.BOLD, enabled=use_color)
        print(f"  {cmd:<34} {theme.paint(description, theme.DIM, enabled=use_color)}")
    print()
    print(theme.paint("Tip: 'wob --json <command>' gives machine-readable output.",
                      theme.DIM, enabled=use_color))
    print()


def maybe_handle_fast_path(argv: List[str]) -> Optional[int]:
    """
    Return an exit code when *argv* is fully handled by the fast path,
    otherwise return None so the real CLI can parse it.
    """
    if not argv:
        print_landing()
        return 0

    # `wob --version` / `wob -V` / `wob version` (plus --json variants)
    if (len(argv) <= 2 and all(a in ("--version", "-V", "version", "--json") for a in argv)
            and any(a in ("--version", "-V", "version") for a in argv)):
        if "--json" in argv:
            print(json.dumps({
                "name": "wobble",
                "command": "wob",
                "version": __version__,
            }))
        else:
            print(_version_text())
        return 0

    return None


def run(argv: Optional[List[str]] = None) -> int:
    """Entry point shared by the installed launcher and ``python -m wobble``."""
    args = list(sys.argv[1:] if argv is None else argv)
    fast = maybe_handle_fast_path(args)
    if fast is not None:
        return fast

    from wobble.cli import main
    return main(args)


if __name__ == "__main__":
    sys.exit(run())
