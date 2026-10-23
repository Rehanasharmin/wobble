"""
Wobble ASCII Theme
A tiny, dependency-free visual identity layer: the wordmark, plain headings,
aligned status words and progress meters drawn with pure ASCII characters.

Everything here is optional: when colour is disabled (``NO_COLOR``, ``--no-color``,
JSON mode, redirected output) the exact same layout is produced without escape
codes, so logs stay readable and machine-parseable.
"""

from __future__ import annotations

import os
import sys

# ---------------------------------------------------------------------------
# Palette (ANSI SGR codes)
# ---------------------------------------------------------------------------
RESET = "0"
BOLD = "1"
DIM = "2"
ITALIC = "3"
UNDERLINE = "4"

BLACK = "30"
RED = "31"
GREEN = "32"
YELLOW = "33"
BLUE = "34"
MAGENTA = "35"
CYAN = "36"
WHITE = "37"

BRIGHT_BLACK = "90"
BRIGHT_RED = "91"
BRIGHT_GREEN = "92"
BRIGHT_YELLOW = "93"
BRIGHT_BLUE = "94"
BRIGHT_MAGENTA = "95"
BRIGHT_CYAN = "96"
BRIGHT_WHITE = "97"

# Gradient used for the wordmark (top line -> bottom line)
BANNER_GRADIENT: Sequence[str] = (BRIGHT_CYAN, CYAN, BLUE, MAGENTA, BRIGHT_MAGENTA)

# ---------------------------------------------------------------------------
# Logo art (pure ASCII, fixed width)
# ---------------------------------------------------------------------------
BANNER_ART: str = r"""
 __        __   ____   ____   ____   _      _____
 \ \      / /  / __ \ |  _ \ | __ ) | |    | ____|
  \ \ /\ / /  | |  | || |_) ||  _ \ | |    |  _|
   \ V  V /   | |__| || |_) || |_) || |___ | |___
    \_/\_/     \____/ |____/ |____/ |_____||_____|
""".strip("\n")

BANNER_WIDTH = max(len(line) for line in BANNER_ART.splitlines())
# Pad to a rectangle so boxes and subtitles align perfectly.
BANNER_ART = "\n".join(line.ljust(BANNER_WIDTH) for line in BANNER_ART.splitlines())

TAGLINE = "Android and web development from Termux"
VERSION_LINE_PREFIX = "wob"

# Compact mark used inside headings / small terminals
MARK = "wob"


# ---------------------------------------------------------------------------
# Capability detection & painting
# ---------------------------------------------------------------------------
def supports_color(stream=None) -> bool:
    """Return True when ANSI colour should be emitted for *stream*."""
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    if os.environ.get("TERM", "") == "dumb":
        return False
    stream = stream if stream is not None else sys.stdout
    try:
        return bool(stream.isatty())
    except Exception:
        return False


def color_enabled(no_color: bool = False, json_mode: bool = False) -> bool:
    if no_color or json_mode:
        return False
    return supports_color()


def paint(text: str, *styles: str, enabled: bool = True) -> str:
    """Wrap *text* in ANSI styles; a no-op when colour is disabled."""
    if not enabled or not styles:
        return text
    return "\033[" + ";".join(styles) + "m" + text + "\033[0m"


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences (used by tests and width calculations)."""
    out: List[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\033" and i + 1 < n and text[i + 1] == "[":
            i += 2
            while i < n and not ("@" <= text[i] <= "~"):
                i += 1
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def visible_len(text: str) -> int:
    return len(strip_ansi(text))


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------
def banner(use_color: bool = True, subtitle: Optional[str] = None) -> str:
    """Return the multi-line ASCII wordmark, optionally with a subtitle."""
    lines = []
    for index, art_line in enumerate(BANNER_ART.splitlines()):
        code = BANNER_GRADIENT[index % len(BANNER_GRADIENT)]
        lines.append(paint(art_line, code, BOLD, enabled=use_color))
    if subtitle is not None:
        pad = max(0, (BANNER_WIDTH - len(subtitle)) // 2)
        lines.append(" " * pad + paint(subtitle, DIM, enabled=use_color))
    return "\n".join(lines)


def rule(title: str = "", width: int = 64, use_color: bool = True,
         color: str = CYAN, fill: str = "-") -> str:
    """Return a plain section heading.

    Titled rules used to be drawn as ``+--[ title ]-----+`` banners. The border
    was visual noise, so a title now renders as a single bold word and an empty
    title renders a subtle divider for places that need one.
    """
    width = max(16, width)
    if not title:
        return paint(fill * width, DIM, enabled=use_color)
    return paint(title, BOLD, color, enabled=use_color)


def box(title: str, rows: Iterable[str], width: int = 64, use_color: bool = True,
        color: str = CYAN) -> str:
    """Render a titled list with no border, so output stays quiet and scannable."""
    width = max(24, width)
    out = []
    if title:
        out.append(rule(title, width=width, use_color=use_color, color=color))
    for row in rows:
        if visible_len(row) > width - 2:
            # Truncate by visible characters while preserving escape sequences.
            row = _truncate_visible(row, width - 3) + "."
        out.append("  " + row)
    return "\n".join(out)


def _truncate_visible(text: str, limit: int) -> str:
    out: List[str] = []
    visible = 0
    i = 0
    n = len(text)
    while i < n and visible < limit:
        if text[i] == "\033" and i + 1 < n and text[i + 1] == "[":
            j = i + 2
            while j < n and not ("@" <= text[j] <= "~"):
                j += 1
            out.append(text[i:j + 1])
            i = j + 1
            continue
        out.append(text[i])
        visible += 1
        i += 1
    return "".join(out)


#: Short, plain status words. No brackets: they read like part of the sentence.
BADGE_WIDTH = 7
_BADGE_TABLE = {
    "ok": ("ok", GREEN),
    "pass": ("ok", GREEN),
    "success": ("ok", GREEN),
    "healthy": ("ok", GREEN),
    "warning": ("warn", YELLOW),
    "warn": ("warn", YELLOW),
    "degraded": ("warn", YELLOW),
    "missing": ("missing", RED),
    "error": ("fail", BRIGHT_RED),
    "fail": ("fail", BRIGHT_RED),
    "critical": ("fail", BRIGHT_RED),
    "broken": ("fail", BRIGHT_RED),
    "info": ("info", CYAN),
    "run": ("run", MAGENTA),
    "skip": ("skip", DIM),
}


def badge(status: str, use_color: bool = True) -> str:
    """Return a plain, fixed-width status word such as ``ok`` or ``warn``."""
    label, code = _BADGE_TABLE.get(str(status).lower(), ("?", DIM))
    return paint(label.ljust(BADGE_WIDTH), code, BOLD, enabled=use_color)


def check(status: str, label: str, detail: str = "", use_color: bool = True,
          label_width: int = 24) -> str:
    """One aligned status row: ``ok  Python           3.11.2``."""
    row = f"{badge(status, use_color)} {label.ljust(label_width)}"
    if detail:
        row += f"  {detail}"
    return row.rstrip()


def progress_bar(percent: float, width: int = 22, use_color: bool = True,
                 invert: bool = False) -> str:
    """ASCII meter: ``[##########------------] 45%``.

    By default high values are "hot" (disk usage). Pass ``invert=True`` for
    health scores, where 100% should be green rather than red.
    """
    percent = max(0.0, min(100.0, float(percent)))
    filled = int(round((percent / 100.0) * width))
    body = "#" * filled + "-" * (width - filled)
    heat = 100.0 - percent if invert else percent
    code = GREEN if heat < 70 else (YELLOW if heat < 90 else RED)
    return (paint("[", DIM, enabled=use_color) + paint(body, code, enabled=use_color)
            + paint("]", DIM, enabled=use_color) + f" {percent:3.0f}%")


def kv(key: str, value: str, use_color: bool = True, width: int = 16) -> str:
    """Aligned ``key: value`` row with a dim key."""
    return f"{paint((key + ':').ljust(width), DIM, enabled=use_color)} {value}"


def list_item(text: str, marker: str = "-", use_color: bool = True) -> str:
    return f"{paint(marker, CYAN, enabled=use_color)} {text}"


def link(url: str, use_color: bool = True) -> str:
    return paint(url, UNDERLINE, BRIGHT_CYAN, enabled=use_color)
