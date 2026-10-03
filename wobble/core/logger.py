"""
Wobble Output & Structured Logging
Provides ANSI colored human-readable outputs and clean JSON mode for AI agents.
"""

import sys
import json
from typing import Any, Optional, Dict


class Logger:
    def __init__(self, json_mode: bool = False, no_color: bool = False):
        self.json_mode = json_mode
        self.use_color = not no_color and sys.stdout.isatty() and not json_mode

        # ANSI color codes
        if self.use_color:
            self.RESET = "\033[0m"
            self.BOLD = "\033[1m"
            self.DIM = "\033[2m"
            self.RED = "\033[31m"
            self.GREEN = "\033[32m"
            self.YELLOW = "\033[33m"
            self.BLUE = "\033[34m"
            self.MAGENTA = "\033[35m"
            self.CYAN = "\033[36m"
        else:
            self.RESET = ""
            self.BOLD = ""
            self.DIM = ""
            self.RED = ""
            self.GREEN = ""
            self.YELLOW = ""
            self.BLUE = ""
            self.MAGENTA = ""
            self.CYAN = ""

    def info(self, msg: str, prefix: str = "ℹ"):
        if not self.json_mode:
            print(f"{self.CYAN}{prefix}{self.RESET} {msg}")

    def success(self, msg: str, prefix: str = "✓"):
        if not self.json_mode:
            print(f"{self.GREEN}{self.BOLD}{prefix}{self.RESET} {msg}")

    def warn(self, msg: str, prefix: str = "⚠"):
        if not self.json_mode:
            print(f"{self.YELLOW}{prefix}{self.RESET} {msg}")

    def error(self, msg: str, prefix: str = "✗"):
        if not self.json_mode:
            print(f"{self.RED}{self.BOLD}{prefix}{self.RESET} {msg}", file=sys.stderr)

    def heading(self, title: str):
        if not self.json_mode:
            print(f"\n{self.BOLD}{self.MAGENTA}==> {title}{self.RESET}")

    def step(self, step_name: str):
        if not self.json_mode:
            print(f"  {self.BLUE}➜{self.RESET} {step_name}")

    def detail(self, key: str, value: Any):
        if not self.json_mode:
            print(f"    {self.DIM}{key}:{self.RESET} {value}")

    def raw(self, msg: str):
        if not self.json_mode:
            print(msg)

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
