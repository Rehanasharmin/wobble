"""
Wobble Output & Structured Logging
Provides ASCII-styled human-readable output and clean JSON mode for AI agents.

The Logger is intentionally tiny: every call is a single ``print`` and colour is
resolved once at construction time, which keeps startup fast on mobile CPUs.
"""

from __future__ import annotations

import sys
import json

from wobble.core import theme


class Logger:
    def __init__(self, json_mode: bool = False, no_color: bool = False):
        self.json_mode = json_mode
        self.use_color = theme.color_enabled(no_color=no_color, json_mode=json_mode)

    # -- primitives --------------------------------------------------------
    def _paint(self, text: str, *styles: str) -> str:
        return theme.paint(text, *styles, enabled=self.use_color)

    def info(self, msg: str, prefix: str = "[i]"):
        if not self.json_mode:
            print(f"{self._paint(prefix, theme.CYAN)} {msg}")

    def success(self, msg: str, prefix: str = "[+]"):
        if not self.json_mode:
            print(f"{self._paint(prefix, theme.GREEN, theme.BOLD)} {msg}")

    def warn(self, msg: str, prefix: str = "[!]"):
        if not self.json_mode:
            print(f"{self._paint(prefix, theme.YELLOW, theme.BOLD)} {msg}")

    def error(self, msg: str, prefix: str = "[x]"):
        if not self.json_mode:
            print(f"{self._paint(prefix, theme.RED, theme.BOLD)} {msg}", file=sys.stderr)

    def heading(self, title: str):
        """Print a compact ASCII section header."""
        if not self.json_mode:
            print()
            print(theme.rule(title, width=64, use_color=self.use_color))
        else:
            pass

    def step(self, step_name: str):
        if not self.json_mode:
            print(f"  {self._paint('->', theme.BLUE)} {step_name}")

    def detail(self, key: str, value: Any):
        if not self.json_mode:
            print(f"    {theme.kv(str(key), str(value), use_color=self.use_color)}")

    def raw(self, msg: str):
        if not self.json_mode:
            print(msg)

    def blank(self):
        if not self.json_mode:
            print()

    def banner(self, subtitle: Optional[str] = None):
        """Print the Wobble ASCII wordmark."""
        if not self.json_mode:
            print(theme.banner(self.use_color, subtitle))

    def hint(self, msg: str):
        if not self.json_mode:
            print(self._paint(msg, theme.DIM))

    def status(self, status: str, label: str, detail: str = ""):
        """Print an aligned ASCII badge row, e.g. ``[ OK ] CPU Architecture ...``."""
        if not self.json_mode:
            suffix = f" {detail}" if detail else ""
            print(f"  {theme.badge(status, self.use_color)} {label}{suffix}")

    def box(self, title: str, rows: Iterable[str], width: int = 64):
        if not self.json_mode:
            print(theme.box(title, rows, width=width, use_color=self.use_color))

    def progress(self, percent: float, label: str = ""):
        if not self.json_mode:
            bar = theme.progress_bar(percent, use_color=self.use_color)
            print(f"  {label} {bar}" if label else f"  {bar}")

    def json_output(self, data: Any):
        """Serialize data to stdout as formatted JSON."""
        print(json.dumps(data, indent=2, default=str))


# Global default logger instance
_logger = Logger()


def get_logger() -> Logger:
    return _logger


def set_logger(logger: Logger):
    global _logger
    _logger = logger
