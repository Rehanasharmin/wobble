"""
Wobble ASCII Theme
A tiny, dependency-free visual identity layer: banners, rules, boxes, status
badges and progress bars drawn with pure ASCII characters.

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

TAGLINE = "Termux -> Wobble -> Projects -> Frameworks -> Build -> Test -> APK/Web"
VERSION_LINE_PREFIX = "wob"

# Compact mark used inside headings / small terminals
MARK = "[wob]"


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
    """Return an ASCII section rule: ``+--[ title ]-----+``."""
    width = max(16, width)
    if not title:
        return paint("+" + fill * (width - 2) + "+", DIM, enabled=use_color)
    label = f"[ {title} ]"
    if len(label) > width - 4:
        label = label[: width - 5] + "]"
    left = 2
    # "+" + left fill + label + right fill + "+" == width
    right = max(0, width - 4 - len(label))
    body = "+" + fill * left + paint(label, BOLD, color, enabled=use_color)
    body += paint(fill * right + "+", DIM, enabled=use_color)
    return body


def box(title: str, rows: Iterable[str], width: int = 64, use_color: bool = True,
        color: str = CYAN) -> str:
    """Draw a lightweight ASCII box around rows of text (ANSI-aware widths)."""
    width = max(24, width)
    out = [rule(title, width=width, use_color=use_color, color=color)]
    inner = width - 4
    for row in rows:
        length = visible_len(row)
        if length > inner:
            # Truncate by visible characters while preserving escape sequences.
            row = _truncate_visible(row, inner - 1) + "."
            length = visible_len(row)
        out.append(paint("| ", DIM, enabled=use_color) + row + " " * (inner - length)
                   + paint(" |", DIM, enabled=use_color))
    out.append(rule("", width=width, use_color=use_color))
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


def badge(status: str, use_color: bool = True) -> str:
    """Return a tag such as ``[ OK ]`` / ``[WARN]`` / ``[MISS]``."""
    table = {
        "ok": ("[ OK ]", GREEN),
        "pass": ("[ OK ]", GREEN),
        "success": ("[ OK ]", GREEN),
        "warning": ("[WARN]", YELLOW),
        "warn": ("[WARN]", YELLOW),
        "missing": ("[MISS]", RED),
        "error": ("[FAIL]", BRIGHT_RED),
        "fail": ("[FAIL]", BRIGHT_RED),
        "info": ("[INFO]", CYAN),
        "run": ("[RUN ]", MAGENTA),
        "skip": ("[SKIP]", DIM),
    }
    label, code = table.get(status.lower(), ("[ ?? ]", DIM))
    return paint(label, code, BOLD, enabled=use_color)


def progress_bar(percent: float, width: int = 22, use_color: bool = True) -> str:
    """ASCII meter: ``[##########>-----------] 45%``."""
    percent = max(0.0, min(100.0, float(percent)))
    filled = int(round((percent / 100.0) * width))
    if filled >= width:
        body = "#" * width
    elif filled <= 0:
        body = "-" * width
    else:
        body = "#" * (filled - 1) + ">" + "-" * (width - filled)
    code = GREEN if percent < 70 else (YELLOW if percent < 90 else RED)
    return (paint("[", DIM, enabled=use_color) + paint(body, code, enabled=use_color)
            + paint("]", DIM, enabled=use_color) + f" {percent:3.0f}%")


def kv(key: str, value: str, use_color: bool = True, width: int = 16) -> str:
    """Aligned ``key: value`` row with a dim key."""
    return f"{paint((key + ':').ljust(width), DIM, enabled=use_color)} {value}"


def list_item(text: str, marker: str = "->", use_color: bool = True) -> str:
    return f"{paint(marker, CYAN, enabled=use_color)} {text}"


def link(url: str, use_color: bool = True) -> str:
    return paint(url, UNDERLINE, BRIGHT_CYAN, enabled=use_color)
