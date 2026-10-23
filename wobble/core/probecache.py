"""Wobble Probe Cache
A tiny, self-invalidating disk cache for expensive environment probes.

``wob doctor`` spends most of its wall time spawning ``--version`` subprocesses.
Tool versions do not change unless the binary changes, so each cache entry is
keyed by the executable path plus its inode fingerprint (mtime + size): a
reinstalled or upgraded tool invalidates itself automatically. Entries also
expire after a TTL so a long-lived phone stays correct.

The cache is deliberately boring: one small JSON file, atomic writes, all
errors ignored. A missing or corrupt cache only costs speed, never correctness.

Environment:
    ``WOBBLE_PROBE_TTL``   seconds before an entry expires (0 disables the cache)
    ``WOBBLE_NO_CACHE``    set to 1 to disable reads and writes entirely
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from wobble.core.context import get_home
from wobble.core.fsutil import atomic_write_json

CACHE_SCHEMA = 1
DEFAULT_TTL = 3600
MAX_ENTRIES = 128

_lock = threading.Lock()
_state = {"loaded": False, "dirty": False, "data": None}


def cache_path() -> Path:
    return get_home() / ".wobble" / "cache" / "probes.json"


def ttl_seconds() -> int:
    """Configured TTL in seconds (0 disables caching)."""
    raw = os.environ.get("WOBBLE_PROBE_TTL")
    if raw is None:
        return DEFAULT_TTL
    try:
        return max(0, int(float(raw)))
    except (TypeError, ValueError):
        return DEFAULT_TTL


def enabled() -> bool:
    if os.environ.get("WOBBLE_NO_CACHE") in ("1", "true", "yes"):
        return False
    return ttl_seconds() > 0


def _load() -> dict:
    if _state["loaded"]:
        # Return the *same* dict so callers can mutate it in place; ``or {}``
        # would hand out a fresh empty dict and silently drop every write.
        return _state["data"] if _state["data"] is not None else {}
    data = {}
    try:
        import json
        with open(cache_path(), "r", encoding="utf-8") as handle:
            parsed = json.load(handle)
        if isinstance(parsed, dict) and isinstance(parsed.get("entries"), dict):
            data = parsed["entries"]
    except (OSError, ValueError):
        data = {}
    _state["loaded"] = True
    _state["data"] = data
    return data


def fingerprint(path: str) -> list:
    """Cheap change detector for an executable: [dev, ino, mtime_ns, size]."""
    try:
        stat = os.stat(path)
        return [stat.st_dev, stat.st_ino, stat.st_mtime_ns, stat.st_size]
    except OSError:
        return []


def get(key: str, fp: list = None, ttl: int = None) -> tuple:
    """Look up *key*. Returns ``(hit, value)``.

    A value is only returned when it is younger than the TTL and its
    fingerprint still matches the current file.
    """
    ttl = ttl_seconds() if ttl is None else ttl
    if ttl <= 0 or not enabled():
        return False, None
    with _lock:
        entries = _load()
        entry = entries.get(key)
        if not isinstance(entry, dict):
            return False, None
        age = time.time() - float(entry.get("at", 0))
        if age < 0 or age > ttl:
            return False, None
        if fp is not None and entry.get("fp") not in (None, fp):
            return False, None
        return True, entry.get("value")


def put(key: str, value, fp: list = None) -> None:
    """Store *value* under *key* (best effort, merges with other processes)."""
    if not enabled():
        return
    with _lock:
        entries = _load()
        entries[key] = {"at": time.time(), "fp": fp, "value": value}
        if len(entries) > MAX_ENTRIES:
            newest = sorted(entries.items(), key=lambda kv: kv[1].get("at", 0), reverse=True)
            entries = dict(newest[:MAX_ENTRIES])
            _state["data"] = entries
        _state["dirty"] = True


def flush() -> bool:
    """Write pending entries to disk. Returns True when a write happened."""
    with _lock:
        if not _state["dirty"] or not _load():
            _state["dirty"] = False
            return False
        data = {
            "schema": CACHE_SCHEMA,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "entries": _state["data"],
        }
        try:
            atomic_write_json(cache_path(), data)
            _state["dirty"] = False
            return True
        except OSError:
            return False


def stats() -> dict:
    """Return counters used by ``wob doctor --timings`` and benchmarks."""
    with _lock:
        entries = _load()
        now = time.time()
        fresh = sum(1 for e in entries.values()
                    if isinstance(e, dict) and now - float(e.get("at", 0)) <= ttl_seconds())
        return {
            "enabled": enabled(),
            "ttl_seconds": ttl_seconds(),
            "entries": len(entries),
            "fresh": fresh,
            "path": str(cache_path()),
            "dirty": bool(_state["dirty"]),
        }


def clear() -> int:
    """Delete the cache file. Returns the number of entries discarded."""
    with _lock:
        entries = _load()
        count = len(entries)
        _state["data"] = {}
        _state["dirty"] = False
    try:
        if cache_path().exists():
            cache_path().unlink()
    except OSError:
        return 0
    return count


def reset_for_tests() -> None:
    """Drop in-process state so tests can swap ``HOME`` between cases."""
    with _lock:
        _state["loaded"] = False
        _state["dirty"] = False
        _state["data"] = None
