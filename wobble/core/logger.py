"""
Wobble Output & Structured Logging
Provides ASCII-styled human-readable output and clean JSON mode for AI agents.

The Logger is intentionally tiny: every call is a single ``print`` and colour is
resolved once at construction time, which keeps startup fast on mobile CPUs.
"""

from __future__ import annotations

import sys

from wobble.core import theme


class Logger:
    def __init__(self, json_mode: bool = False, no_color: bool = False):
        self.json_mode = json_mode
        self.use_color = theme.color_enabled(no_color=no_color, json_mode=json_mode)
        # JSON errors are emitted once by the CLI boundary. Keeping them here
        # prevents a failed command from exiting non-zero with no JSON at all,
        # while ``_json_emitted`` avoids duplicate documents when a handler has
        # already returned a structured failure result.
        self.errors = []
        self.warnings = []
        self._json_emitted = False

    # -- primitives --------------------------------------------------------
    def _paint(self, text: str, *styles: str) -> str:
        return theme.paint(text, *styles, enabled=self.use_color)

    def _say(self, label: str, color: str, msg: str, stream=None):
        """Print a short coloured word instead of bracket decorations."""
        print(f"{self._paint(label.ljust(5), color, theme.BOLD)} {msg}",
              file=stream or sys.stdout)

    def info(self, msg: str, prefix: str = "info"):
        if not self.json_mode:
            self._say("info", theme.CYAN, msg)

    def success(self, msg: str, prefix: str = "ok"):
        if not self.json_mode:
            self._say("ok", theme.GREEN, msg)

    def warn(self, msg: str, prefix: str = "warn"):
        self.warnings.append(str(msg))
        if not self.json_mode:
            self._say("warn", theme.YELLOW, msg)

    def error(self, msg: str, prefix: str = "error"):
        self.errors.append(str(msg))
        if not self.json_mode:
            self._say("error", theme.RED, msg, stream=sys.stderr)

    def heading(self, title: str):
        """Print a quiet section heading (no border, no filler characters)."""
        if not self.json_mode:
            print()
            print(self._paint(title, theme.BOLD))

    def step(self, step_name: str):
        if not self.json_mode:
            print(f"  {self._paint('-', theme.BLUE)} {step_name}")

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
        """Print one aligned status row, e.g. ``ok   manifest   verified``."""
        if not self.json_mode:
            print("  " + theme.check(status, label, detail, use_color=self.use_color,
                                     label_width=18))

    def box(self, title: str, rows: Iterable[str], width: int = 64):
        if not self.json_mode:
            print(theme.box(title, rows, width=width, use_color=self.use_color))

    def progress(self, percent: float, label: str = ""):
        if not self.json_mode:
            bar = theme.progress_bar(percent, use_color=self.use_color)
            print(f"  {label} {bar}" if label else f"  {bar}")

    def json_output(self, data: Any):
        """Serialize one JSON document and normalize legacy failure results."""
        import json

        if isinstance(data, dict):
            data = dict(data)
            if data.get("success") is False and data.get("error") and "error_code" not in data:
                # Older domain handlers return useful failure dictionaries but
                # do not all know about the shared error contract.
                data["error_code"] = "command_failed"
            if self.warnings:
                existing = data.get("warnings", [])
                if not isinstance(existing, list):
                    existing = [str(existing)]
                data["warnings"] = existing + [
                    warning for warning in self.warnings if warning not in existing
                ]
        rendered = json.dumps(data, indent=2, default=str)
        self._json_emitted = True
        print(rendered)


# Global default logger instance
_logger = Logger()


def get_logger() -> Logger:
    return _logger


def set_logger(logger: Logger):
    global _logger
    _logger = logger
