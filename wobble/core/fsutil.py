"""
Wobble Filesystem Utilities
Crash-safe atomic file writes that prevent corrupted JSON/config files when a
process is interrupted mid-write (common on mobile devices with aggressive
process killers).
"""

from __future__ import annotations

import os
from pathlib import Path


def atomic_write_text(target: Union[str, Path], content: str, encoding: str = "utf-8") -> None:
    """
    Write text to target atomically: data goes to a temporary file in the same
    directory first, then is renamed over the destination. A crash mid-write can
    therefore never leave a half-written target file.
    """
    import tempfile

    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(target.parent),
        prefix=f".{target.name}.",
        suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, target)
    except BaseException:
        # Never leave stray temp files behind on failure or Ctrl+C.
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def atomic_write_json(target: Union[str, Path], data: Any, indent: int = 2) -> None:
    """Serialize data as JSON and write it to target atomically."""
    import json

    atomic_write_text(target, json.dumps(data, indent=indent, default=str) + "\n")


def backup_corrupted_file(target: Union[str, Path]) -> Path:
    """Move a corrupt file aside without overwriting an earlier backup.

    Failures deliberately propagate: callers must not replace the original when
    they could not preserve it. The first backup keeps the historical
    ``.corrupt.bak`` name; later recoveries use ``.corrupt.bak.1``, etc.
    """
    target = Path(target)
    base = target.with_name(target.name + ".corrupt.bak")
    backup = base
    counter = 1
    while backup.exists():
        backup = target.with_name(base.name + f".{counter}")
        counter += 1
    os.replace(target, backup)
    return backup
