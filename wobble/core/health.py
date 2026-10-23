"""Wobble Health Ledger
Persistent memory for things that went wrong and for how the environment looked
the last time it was inspected.

Two small JSON documents live under ``~/.wobble/health/``:

``incidents.json``
    A capped ledger of unexpected failures (crashes, broken installs, failed
    repairs). ``wob self status`` reads it, so a crash that happened yesterday
    still shows up as an actionable warning today instead of being lost in a
    terminal scrollback.

``doctor-baseline.json``
    The previous ``wob doctor`` result plus the time each check last changed
    state. That is what makes regression detection possible: a check that just
    flipped from ``ok`` to ``missing`` is reported as a *regression*, while a
    check that has been failing for three days is reported as *persistent*.

Everything in this module is best-effort and side-effect free for readers: a
permission error, a full disk, or a corrupt ledger must never break a command.
"""

from __future__ import annotations

import time
from pathlib import Path

from wobble.core.context import get_home
from wobble.core.fsutil import atomic_write_json

LEDGER_SCHEMA = 1
MAX_INCIDENTS = 40
MAX_MESSAGE = 400
SNAPSHOT_SCHEMA = 1

# Status severity ordering shared by the doctor and the self-check engine.
STATUS_RANK = {"ok": 0, "info": 0, "warning": 1, "missing": 2, "error": 3}


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
def health_dir() -> Path:
    """Return the directory holding Wobble's local health records."""
    return get_home() / ".wobble" / "health"


def incidents_path() -> Path:
    return health_dir() / "incidents.json"


def snapshot_path() -> Path:
    return health_dir() / "doctor-baseline.json"


def _read_json(path: Path) -> dict:
    import json

    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_json(path: Path, data: dict) -> bool:
    try:
        atomic_write_json(path, data)
        return True
    except (OSError, ValueError):
        return False


def _now() -> float:
    return time.time()


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def human_age(epoch: float, now: float = None) -> str:
    """Render a compact age such as ``12s``, ``4m``, ``3h``, ``2d``."""
    if not epoch:
        return "unknown"
    seconds = max(0, int((now if now is not None else _now()) - epoch))
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h"
    return f"{hours // 24}d"


def _clean_message(message: str) -> str:
    """Keep incident text short, single-line, and free of the home path."""
    text = " ".join(str(message).split())
    home = str(get_home())
    if home and home != "/":
        text = text.replace(home, "~")
    if len(text) > MAX_MESSAGE:
        text = text[: MAX_MESSAGE - 3] + "..."
    return text


# ---------------------------------------------------------------------------
# Incident ledger
# ---------------------------------------------------------------------------
def record_incident(kind: str, message: str, details: dict = None) -> bool:
    """Append one incident, merging identical repeats into a counter.

    Returns ``True`` when the ledger was written. Never raises: recording a
    diagnostic must not turn a working command into a failing one.
    """
    try:
        path = incidents_path()
        data = _read_json(path)
        incidents = data.get("incidents")
        if not isinstance(incidents, list):
            incidents = []

        now = _now()
        kind = _clean_message(kind)[:64] or "error"
        message = _clean_message(message)
        key = (kind, message)

        merged = False
        for entry in incidents:
            if not isinstance(entry, dict):
                continue
            if entry.get("kind") == kind and entry.get("message") == message:
                entry["count"] = int(entry.get("count", 1)) + 1
                entry["last_seen"] = now
                entry["last_seen_iso"] = _iso(now)
                merged = True
                break

        if not merged:
            incidents.append(
                {
                    "kind": kind,
                    "message": message,
                    "count": 1,
                    "first_seen": now,
                    "first_seen_iso": _iso(now),
                    "last_seen": now,
                    "last_seen_iso": _iso(now),
                    "details": details if isinstance(details, dict) else {},
                }
            )

        # Newest first, capped: the ledger is a diagnostic aid, not a log file.
        incidents.sort(key=lambda item: item.get("last_seen", 0), reverse=True)
        data = {
            "schema": LEDGER_SCHEMA,
            "updated_at": _iso(now),
            "incidents": incidents[:MAX_INCIDENTS],
            "total_recorded": int(data.get("total_recorded", 0)) + (0 if merged else 1),
        }
        return _write_json(path, data)
    except Exception:
        return False


def read_incidents(limit: int = 10) -> list:
    """Return the most recent incidents (newest first)."""
    data = _read_json(incidents_path())
    incidents = data.get("incidents")
    if not isinstance(incidents, list):
        return []
    clean = [item for item in incidents if isinstance(item, dict)]
    clean.sort(key=lambda item: item.get("last_seen", 0), reverse=True)
    return clean[: max(0, int(limit))]


def incident_summary(limit: int = 5, window_hours: float = 24 * 7) -> dict:
    """Summarize the ledger for the self-check and the doctor.

    ``recent`` counts incidents inside *window_hours*; ``total`` counts every
    distinct incident ever recorded (not merged repeats).
    """
    data = _read_json(incidents_path())
    incidents = [item for item in data.get("incidents", []) if isinstance(item, dict)]
    incidents.sort(key=lambda item: item.get("last_seen", 0), reverse=True)
    now = _now()
    cutoff = now - window_hours * 3600
    recent = [item for item in incidents if item.get("last_seen", 0) >= cutoff]
    return {
        "total": len(incidents),
        "recent": len(recent),
        "window_hours": window_hours,
        "last": incidents[0] if incidents else None,
        "last_age": human_age(incidents[0].get("last_seen", 0), now) if incidents else None,
        "entries": incidents[: max(0, int(limit))],
        "repeat_count": sum(int(item.get("count", 1)) for item in recent),
    }


def clear_incidents() -> int:
    """Delete the ledger. Returns the number of incidents removed."""
    data = _read_json(incidents_path())
    count = len([i for i in data.get("incidents", []) if isinstance(i, dict)])
    try:
        if incidents_path().exists():
            incidents_path().unlink()
    except OSError:
        return 0
    return count


# ---------------------------------------------------------------------------
# Doctor snapshots and regression detection
# ---------------------------------------------------------------------------
def _status_map(checks) -> dict:
    """Normalize a report (or a list of check dicts) into ``{name: status}``."""
    mapping = {}
    for check in checks or []:
        if not isinstance(check, dict):
            continue
        name = check.get("name") or check.get("code")
        status = check.get("status")
        if name and status:
            mapping[str(name)] = str(status)
    return mapping


def _build_entries(current: dict, previous_checks: dict, now: float) -> dict:
    """Merge current statuses with the previous ``since`` timestamps."""
    entries = {}
    for name, status in current.items():
        old = previous_checks.get(name)
        old_status = old.get("status") if isinstance(old, dict) else None
        if isinstance(old, dict) and old_status == status:
            since = float(old.get("since", now))
        else:
            since = now
        entries[name] = {"status": status, "since": since, "since_iso": _iso(since)}
    return entries


def save_snapshot(report_or_checks, path: Path = None) -> bool:
    """Persist the current check statuses as the new baseline."""
    path = path or snapshot_path()
    checks = report_or_checks.get("checks") if isinstance(report_or_checks, dict) else report_or_checks
    current = _status_map(checks)
    previous = _read_json(path)
    previous_checks = previous.get("checks") if isinstance(previous.get("checks"), dict) else {}
    now = _now()
    data = {
        "schema": SNAPSHOT_SCHEMA,
        "updated_at": _iso(now),
        "updated_at_epoch": now,
        "checks": _build_entries(current, previous_checks, now),
    }
    return _write_json(path, data)


def diff_and_update(report_or_checks, path: Path = None, save: bool = True) -> dict:
    """Compare checks with the last snapshot and (optionally) advance it.

    Each check remembers ``since``: the moment its status last changed. That
    keeps *persistent* problems distinct from fresh regressions.
    """
    path = path or snapshot_path()
    checks = report_or_checks.get("checks") if isinstance(report_or_checks, dict) else report_or_checks
    current = _status_map(checks)
    previous = _read_json(path)
    previous_checks = previous.get("checks") if isinstance(previous.get("checks"), dict) else {}
    now = _now()
    entries = _build_entries(current, previous_checks, now)

    diff = compare_snapshots(
        {"checks": previous_checks},
        {"checks": entries},
        previous_at=previous.get("updated_at_epoch"),
        now=now,
    )
    if save:
        _write_json(path, {
            "schema": SNAPSHOT_SCHEMA,
            "updated_at": _iso(now),
            "updated_at_epoch": now,
            "checks": entries,
        })
    return diff


def load_snapshot(path: Path = None) -> dict:
    """Return the stored doctor snapshot, or an empty dict."""
    return _read_json(path or snapshot_path())


def _snapshot_entries(snapshot: dict) -> dict:
    """Accept either ``{name: status}`` or ``{name: {status, since}}``."""
    checks = snapshot.get("checks") if isinstance(snapshot, dict) else None
    if not isinstance(checks, dict):
        return {}
    out = {}
    for name, value in checks.items():
        if isinstance(value, dict):
            out[name] = str(value.get("status", "ok"))
        else:
            out[name] = str(value)
    return out


def compare_snapshots(previous: dict, current: dict, previous_at: float = None,
                      now: float = None) -> dict:
    """Diff two check-status snapshots.

    Returns ``regressions`` (worse), ``recovered`` (better), ``new`` checks,
    ``removed`` checks, and ``persistent`` failures whose status has not
    changed for longer than a day.
    """
    now = now if now is not None else _now()
    before = _snapshot_entries(previous)
    after = _snapshot_entries(current)
    previous_checks = (previous or {}).get("checks") or {}
    current_checks = (current or {}).get("checks") or {}

    regressions, recovered, new, removed, persistent = [], [], [], [], []
    for name, status in after.items():
        rank_new = STATUS_RANK.get(status, 1)
        if name not in before:
            if rank_new > 0:
                new.append({"name": name, "status": status})
            continue
        rank_old = STATUS_RANK.get(before[name], 1)
        if rank_new > rank_old:
            regressions.append({"name": name, "from": before[name], "to": status})
        elif rank_new < rank_old:
            recovered.append({"name": name, "from": before[name], "to": status})
        if rank_new > 0:
            entry = current_checks.get(name)
            since = entry.get("since") if isinstance(entry, dict) else None
            if since is not None and (now - float(since)) >= 86400:
                persistent.append({
                    "name": name,
                    "status": status,
                    "since_iso": _iso(float(since)),
                    "days": int((now - float(since)) // 86400),
                })
    for name, status in before.items():
        if name not in after:
            removed.append({"name": name, "status": status})

    return {
        "regressions": regressions,
        "recovered": recovered,
        "new": new,
        "removed": removed,
        "persistent": persistent,
        "previous_at": _iso(previous_at) if previous_at else None,
        "compared_at": _iso(now),
    }


def clear_snapshot() -> bool:
    """Remove the stored doctor snapshot."""
    try:
        if snapshot_path().exists():
            snapshot_path().unlink()
        return True
    except OSError:
        return False
