"""Wobble Self-Check Engine
One fast, structured pass that answers the only question that matters about an
installed command-line tool: *is this thing still intact?*

``wob self status`` used to report three booleans. This module replaces that with
a real diagnostic sweep that runs in a few milliseconds:

* manifest presence, schema, and version drift (mixed installs)
* missing or resized runtime files (without hashing — deep mode hashes)
* bytecode cache coverage (missing ``.pyc`` means a slow first run)
* launcher existence, marker, executable bit, and *target* path (stale after a
  reinstall into a different prefix)
* PATH presence and launcher shadowing by another ``wob``
* shell completions, config/registry JSON validity, and directory writability
* free disk space, shared-storage/noexec warnings, and interrupted-install
  leftovers (``.app.tmp-*``, ``.app.old``)
* the incident ledger recorded by crashes and failed repairs
* optional deep verification: SHA-256 of every installed file, plus an import
  smoke test of the heavy subcommand modules

Everything is returned as structured findings with stable ``code`` values so
agents and CI can assert on them, and every problem carries a copy-paste fix.
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from wobble import __version__
from wobble.core import health, installer
from wobble.core.context import (
    get_home,
    get_mount_info,
    get_python_info,
    is_termux,
)
from wobble.core.fsutil import backup_corrupted_file

MIN_PYTHON = (3, 8)
RANK = {"ok": 0, "info": 0, "warning": 1, "critical": 2}
_BAD = ("warning", "critical")

# Runtime modules exercised by the deep smoke test. These are the heavyweight
# entry points that a partially copied or corrupt install breaks first.
SMOKE_MODULES = (
    "wobble.cli",
    "wobble.core.doctor",
    "wobble.core.installer",
    "wobble.web.manager",
    "wobble.android.apk",
    "wobble.deps.manager",
    "wobble.plugins",
)


class Finding:
    """One diagnostic result."""

    __slots__ = ("code", "title", "status", "detail", "fix", "data")

    def __init__(self, code: str, title: str, status: str, detail: str = "",
                 fix: str = None, data: dict = None):
        self.code = code
        self.title = title
        self.status = status if status in RANK else "warning"
        self.detail = detail
        self.fix = fix
        self.data = data or {}

    def to_dict(self) -> dict:
        payload = {
            "code": self.code,
            "title": self.title,
            "status": self.status,
            "detail": self.detail,
        }
        if self.fix:
            payload["fix"] = self.fix
        if self.data:
            payload["data"] = self.data
        return payload


def _finding(checks: list, timings: dict, code: str, title: str, status: str,
             detail: str = "", fix: str = None, data: dict = None) -> Finding:
    """Append a finding. ``timings`` is retained for API symmetry and for the
    few grouped measurements that are recorded explicitly."""
    finding = Finding(code, title, status, detail, fix, data)
    checks.append(finding)
    return finding


# ---------------------------------------------------------------------------
# Small helpers (no subprocesses, no hashing)
# ---------------------------------------------------------------------------
def _human_bytes(value: float) -> str:
    value = float(value or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} TB"


def _read_json(path: Path):
    """Return ``(data, error)`` for a JSON file; ``(None, None)`` when absent."""
    if not path.is_file():
        return None, None
    import json

    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data, None
    except (OSError, ValueError) as exc:
        return None, str(exc)


def _launcher_app_path(path: Path):
    """Extract the ``APP=`` path from a generated launcher script."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            head = handle.read(4096)
    except OSError:
        return None
    for line in head.splitlines():
        if line.startswith("APP="):
            return line.split("=", 1)[1].strip().strip("'\"")
    return None


def _pyc_coverage(app_dir: Path):
    """Return ``(missing_count, total_sources)`` for the installed package."""
    package = app_dir / "wobble"
    if not package.is_dir():
        return 0, 0
    missing = 0
    total = 0
    for dirpath, _dirnames, filenames in os.walk(package):
        cache_dir = Path(dirpath) / "__pycache__"
        cached = set()
        try:
            cached = {name.split(".")[0] for name in os.listdir(cache_dir)
                      if name.endswith(".pyc")}
        except OSError:
            cached = set()
        for name in filenames:
            if not name.endswith(".py"):
                continue
            total += 1
            if Path(name).stem not in cached:
                missing += 1
    return missing, total


def _manifest_summary(manifest: dict) -> dict:
    files = manifest.get("files") if isinstance(manifest.get("files"), dict) else {}
    return {
        "file_count": len(files),
        "total_bytes": int(manifest.get("total_bytes", 0) or 0),
        "version": manifest.get("version"),
        "schema": manifest.get("schema"),
        "installed_at": manifest.get("installed_at"),
        "launchers": manifest.get("launchers") or [],
        "completions": manifest.get("completions") or [],
        "source": manifest.get("source"),
    }


def _path_analysis(bin_dir: Path, launchers: list) -> dict:
    """Inspect PATH for the bin dir, dead entries, duplicates, and shadowing."""
    entries = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    resolved = []
    dead = []
    seen = set()
    duplicates = []
    for entry in entries:
        try:
            real = str(Path(entry).resolve())
        except OSError:
            real = entry
        if real in seen:
            duplicates.append(entry)
            continue
        seen.add(real)
        if not os.path.isdir(entry):
            dead.append(entry)
        resolved.append((entry, real))

    our = set()
    for candidate in [bin_dir / installer.LAUNCHER_NAME, *[Path(p) for p in launchers]]:
        try:
            our.add(str(candidate.resolve()))
        except OSError:
            our.add(str(candidate))

    which = shutil.which("wob")
    which_real = None
    if which:
        try:
            which_real = str(Path(which).resolve())
        except OSError:
            which_real = which

    return {
        "entries": entries,
        "bin_dir": str(bin_dir),
        "in_path": str(bin_dir) in entries,
        "dead": dead,
        "duplicates": duplicates,
        "which": which,
        "which_real": which_real,
        "ours": sorted(our),
        "shadowed": bool(which_real and our and which_real not in our),
    }


def _nearest_writable(path: Path) -> bool:
    """True when the closest existing ancestor of *path* is writable."""
    current = path
    for _ in range(40):
        try:
            if current.exists():
                return os.access(str(current), os.W_OK)
        except OSError:
            return False
        if current.parent == current:
            break
        current = current.parent
    return False


def config_path() -> Path:
    return get_home() / ".config" / "wobble" / "config.json"


def registry_path() -> Path:
    return get_home() / ".wobble" / "projects.json"


# ---------------------------------------------------------------------------
# Deep helpers
# ---------------------------------------------------------------------------
def _smoke_imports() -> dict:
    """Import the heavy subcommand modules to prove the runtime can load them."""
    import importlib

    failed = []
    loaded = []
    for name in SMOKE_MODULES:
        try:
            importlib.import_module(name)
            loaded.append(name)
        except Exception as exc:  # noqa: BLE001 - report any import failure
            failed.append({"module": name, "error": f"{type(exc).__name__}: {exc}"})
    return {"ok": not failed, "loaded": len(loaded), "failed": failed, "total": len(SMOKE_MODULES)}


# ---------------------------------------------------------------------------
# Main inspection
# ---------------------------------------------------------------------------
def _add_history_check(checks: list, timings: dict) -> None:
    """Record the incident ledger as a finding (used in both install modes)."""
    incident_summary = health.incident_summary()
    if incident_summary["recent"]:
        last = incident_summary.get("last") or {}
        status = "warning"
        if incident_summary["recent"] >= 3 and incident_summary.get("repeat_count", 0) >= 5:
            status = "critical"
        _finding(
            checks, timings, "history.incidents", "Recent failures", status,
            f"{incident_summary['recent']} incident(s), last {incident_summary['last_age']} ago: "
            f"{(last.get('message') or '')[:90]}",
            "wob self incidents   # full ledger; 'wob doctor' explains the last failure",
            incident_summary,
        )
    else:
        _finding(checks, timings, "history.incidents", "Recent failures", "ok",
                 "none recorded", None, {"total": incident_summary["total"]})


def inspect(deep: bool = False, install_root: Path = None, bin_dir: Path = None,
            workers: int = None) -> dict:
    """Run the self-check sweep and return a structured report.

    ``deep`` additionally hashes every installed file and imports the heavy
    modules. The default path touches only the filesystem metadata needed to
    prove the install still works.
    """
    started = time.monotonic()
    checks: list = []
    timings: dict = {}

    root = Path(install_root).expanduser().resolve() if install_root else installer.default_install_root()
    bin_path = Path(bin_dir).expanduser().resolve() if bin_dir else installer.default_bin_dir()
    python = get_python_info()

    # -- interpreter ------------------------------------------------
    t0 = time.monotonic()
    version_ok = tuple(python["version_info"][:2]) >= MIN_PYTHON
    _finding(
        checks, timings, "python.interpreter",
        "Python interpreter",
        "ok" if version_ok else "critical",
        f"Python {python['version']} ({python['implementation']}) at {python['executable']}",
        None if version_ok else "Install Python 3.8 or newer: pkg install -y python",
        {"version": python["version"], "executable": python["executable"]},
    )

    # -- install mode / manifest -------------------------------------
    manifest_path = installer.manifest_path(root)
    manifest = installer.read_manifest(root)
    legacy_target = None
    legacy_launcher = bin_path / installer.LAUNCHER_NAME
    try:
        if legacy_launcher.is_symlink():
            legacy_target = os.readlink(str(legacy_launcher))
    except OSError:
        legacy_target = None

    if not manifest:
        if legacy_target:
            mode = "legacy-symlink"
            _finding(
                checks, timings, "install.manifest", "Install manifest",
                "warning",
                f"Legacy symlink -> {legacy_target}",
                "wob self install   (a symlink breaks when the checkout is deleted)",
                {"path": str(manifest_path)},
            )
        else:
            mode = "source-checkout"
            _finding(
                checks, timings, "install.manifest", "Install manifest",
                "info",
                "Running from a source checkout (not installed as software)",
                "wob self install   (or: sh install.sh)",
                {"path": str(manifest_path), "source": str(installer.package_root())},
            )
        _add_history_check(checks, timings)
        report = _finish_report(
            checks, timings, started, mode=mode, root=root, bin_path=bin_path,
            app_dir=None, manifest=None, deep=deep, python=python,
        )
        report["path"] = {
            "bin_dir": str(bin_path),
            "in_path": str(bin_path) in os.environ.get("PATH", "").split(os.pathsep),
            "which": shutil.which("wob"),
            "shadowed": False,
        }
        report["source"] = {"path": str(installer.package_root()), "exists": True}
        report["legacy_target"] = legacy_target
        return report

    mode = "standalone"
    summary = _manifest_summary(manifest)
    root = Path(manifest.get("install_root", root))
    app_dir = Path(manifest.get("app_dir", root / installer.APP_DIRNAME))
    launchers = [str(p) for p in (manifest.get("launchers") or [])]
    primary_launcher = Path(manifest.get("launcher", bin_path / installer.LAUNCHER_NAME))
    bin_path = primary_launcher.parent

    schema = manifest.get("schema")
    _finding(
        checks, timings, "install.manifest", "Install manifest",
        "ok" if schema == installer.INSTALL_SCHEMA else "warning",
        f"{manifest_path} (schema {schema})" if schema == installer.INSTALL_SCHEMA
        else f"{manifest_path} (unexpected schema {schema!r})",
        None if schema == installer.INSTALL_SCHEMA else "wob self install   # rewrite the manifest",
        {"path": str(manifest_path), "schema": schema},
    )

    manifest_version = manifest.get("version")
    version_matches = manifest_version == __version__
    _finding(
        checks, timings, "install.version", "Installed version",
        "ok" if version_matches else "warning",
        f"v{__version__}" + ("" if version_matches else f" (manifest says v{manifest_version})"),
        None if version_matches else "wob self install   # mixed install: runtime and manifest disagree",
        {"running": __version__, "manifest": manifest_version},
    )

    # -- runtime tree ------------------------------------------------
    t0 = time.monotonic()
    files = manifest.get("files") if isinstance(manifest.get("files"), dict) else {}
    runtime_ok = bool(
        app_dir.is_dir()
        and (app_dir / "wob.py").is_file()
        and (app_dir / "wobble" / "cli.py").is_file()
    )
    missing = []
    resized = []
    for rel, meta in files.items():
        target = app_dir / rel
        try:
            stat_result = target.stat()
        except OSError:
            missing.append(rel)
            continue
        if not target.is_file():
            missing.append(rel)
        elif int(meta.get("size", -1)) != stat_result.st_size:
            resized.append(rel)
    checked = len(files) - len(missing) - len(resized)
    runtime_status = "ok"
    if not runtime_ok or missing:
        runtime_status = "critical"
    elif resized:
        runtime_status = "warning"
    detail = f"{checked}/{len(files)} files intact ({_human_bytes(summary['total_bytes'])})"
    if missing:
        detail = f"{len(missing)} of {len(files)} files missing"
    elif resized:
        detail = f"{len(resized)} of {len(files)} files changed size"
    _finding(
        checks, timings, "runtime.files", "Runtime files", runtime_status, detail,
        None if runtime_status == "ok" else "wob self repair   (or reinstall: wob self install)",
        {
            "app_dir": str(app_dir),
            "checked": checked,
            "missing": missing[:20],
            "changed": resized[:20],
            "missing_count": len(missing),
            "changed_count": len(resized),
        },
    )
    timings["runtime.files"] = round((time.monotonic() - t0) * 1000, 2)

    # Bytecode coverage
    pyc_missing, pyc_total = _pyc_coverage(app_dir)
    if pyc_total == 0:
        _finding(checks, timings, "runtime.bytecode", "Bytecode cache", "warning",
                 "No Python sources found in the installed runtime",
                 "wob self install")
    elif pyc_missing:
        _finding(checks, timings, "runtime.bytecode", "Bytecode cache", "warning",
                 f"{pyc_missing}/{pyc_total} modules not precompiled (slower startup)",
                 "wob self repair --compile",
                 {"missing": pyc_missing, "total": pyc_total})
    else:
        _finding(checks, timings, "runtime.bytecode", "Bytecode cache", "ok",
                 f"all {pyc_total} modules precompiled",
                 None, {"missing": 0, "total": pyc_total})

    # Unexpected files inside the runtime (a stray module can shadow the install)
    known = set(files)
    extras = []
    if app_dir.is_dir():
        for dirpath, dirnames, filenames in os.walk(app_dir):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for name in filenames:
                if name.endswith((".pyc", ".pyo")):
                    continue
                rel = (Path(dirpath) / name).relative_to(app_dir).as_posix()
                if rel not in known:
                    extras.append(rel)
    _finding(
        checks, timings, "runtime.extras", "Unexpected runtime files",
        "ok" if not extras else "warning",
        "none" if not extras else f"{len(extras)} file(s) not in the manifest",
        None if not extras else "wob self verify --json   # inspect, then reinstall if unexpected",
        {"extras": extras[:20], "count": len(extras)},
    )

    # Permissions / readability
    readable = os.access(str(app_dir), os.R_OK | os.X_OK)
    _finding(
        checks, timings, "runtime.permissions", "Runtime permissions",
        "ok" if readable else "critical",
        "readable and traversable" if readable else "not readable by this user",
        None if readable else f"chmod -R u+rwX {app_dir}",
        {"app_dir": str(app_dir)},
    )

    # -- launcher ----------------------------------------------------
    launcher_state = installer._launcher_state(primary_launcher)
    launcher_exists = launcher_state["exists"]
    launcher_ours = launcher_state["is_ours"]
    launcher_exec = launcher_state["executable"]
    launcher_target = launcher_state["app_dir"]
    launcher_status = "ok"
    launcher_detail = f"{primary_launcher} -> {launcher_target or 'unknown'}"
    launcher_fix = None
    if not launcher_exists:
        launcher_status, launcher_detail = "critical", f"missing: {primary_launcher}"
        launcher_fix = "wob self repair"
    elif not launcher_ours:
        launcher_status, launcher_detail = "warning", f"{primary_launcher} was not written by Wobble"
        launcher_fix = f"wob self repair   # or remove {primary_launcher} and reinstall"
    elif not launcher_exec:
        launcher_status, launcher_detail = "warning", f"{primary_launcher} is not executable"
        launcher_fix = f"chmod 755 {primary_launcher}   (or: wob self repair)"
    elif launcher_target and launcher_target != str(app_dir):
        launcher_status = "critical"
        launcher_detail = f"{primary_launcher} points at {launcher_target}, expected {app_dir}"
        launcher_fix = "wob self repair   # rewrite the launcher for this app directory"
    _finding(
        checks, timings, "launcher.present", "Launcher", launcher_status, launcher_detail,
        launcher_fix,
        {"path": str(primary_launcher), "target": launcher_target,
         "executable": launcher_exec, "ours": launcher_ours},
    )

    # -- PATH & shadowing -------------------------------------------
    path_info = _path_analysis(bin_path, launchers)
    if not path_info["in_path"]:
        _finding(
            checks, timings, "launcher.path", "PATH entry", "warning",
            f"{bin_path} is not on PATH",
            f'Add to ~/.bashrc: export PATH="{bin_path}:$PATH"   (or: wob self repair --path)',
            {"bin_dir": str(bin_path)},
        )
    elif path_info["shadowed"]:
        _finding(
            checks, timings, "launcher.path", "PATH entry", "warning",
            f"'wob' resolves to {path_info['which']} instead of {primary_launcher}",
            f"Remove {path_info['which']} or move {bin_path} earlier in PATH",
            {"which": path_info["which"], "expected": str(primary_launcher)},
        )
    else:
        _finding(checks, timings, "launcher.path", "PATH entry", "ok",
                 f"{bin_path} is on PATH" if path_info["which"] else
                 f"{bin_path} is on PATH (launcher not resolved yet: open a new shell)",
                 None, {"bin_dir": str(bin_path)})

    # Dead PATH entries are a real (if minor) problem: they slow lookups and
    # hide a missing install. Duplicate entries are harmless — on Debian /bin is
    # a symlink to /usr/bin, which would otherwise warn on every healthy device.
    bit = f"{len(path_info['dead'])} missing directories"
    if path_info["duplicates"]:
        bit += f", {len(path_info['duplicates'])} duplicate path(s)"
    _finding(
        checks, timings, "environment.path", "PATH integrity",
        "warning" if path_info["dead"] else "ok",
        bit if path_info["dead"] else f"{len(path_info['entries'])} clean entries",
        "Remove dead entries from PATH in ~/.bashrc" if path_info["dead"] else None,
        {"dead": path_info["dead"][:10], "duplicates": path_info["duplicates"][:10]},
    )

    # -- completions -------------------------------------------------
    completions = [Path(p) for p in (manifest.get("completions") or [])]
    if completions:
        broken = [str(p) for p in completions if not p.is_file()]
        _finding(
            checks, timings, "shell.completions", "Shell completions",
            "ok" if not broken else "warning",
            f"{len(completions) - len(broken)}/{len(completions)} installed" if broken
            else f"{len(completions)} installed",
            None if not broken else "wob self repair --completions",
            {"files": [str(p) for p in completions], "missing": broken},
        )
    else:
        _finding(checks, timings, "shell.completions", "Shell completions", "info",
                 "not installed", "wob self install   # completions are optional")

    # -- data & config ----------------------------------------------
    data_dir = get_home() / ".wobble"
    writable = _nearest_writable(data_dir)
    _finding(
        checks, timings, "data.writable", "Data directory",
        "ok" if writable else "warning",
        f"{data_dir} is writable" if writable else f"{data_dir} is read-only",
        None if writable else f"chmod -R u+rwX {data_dir}",
        {"path": str(data_dir)},
    )

    corrupt = []
    for label, path in (("config", config_path()), ("registry", registry_path())):
        _data, error = _read_json(path)
        if error:
            corrupt.append({"file": label, "path": str(path), "error": error})
    _finding(
        checks, timings, "data.config", "Config and registry",
        "ok" if not corrupt else "warning",
        "valid" if not corrupt else ", ".join(f"{c['file']} is corrupt" for c in corrupt),
        None if not corrupt else "wob self repair --config   (keeps a .corrupt.bak copy)",
        {"corrupt": corrupt},
    )

    # -- resources ---------------------------------------------------
    try:
        usage = shutil.disk_usage(str(root if root.exists() else get_home()))
        free = usage.free
        free_status = "ok"
        if free < 5 * 1024 * 1024:
            free_status = "critical"
        elif free < 100 * 1024 * 1024:
            free_status = "warning"
        _finding(
            checks, timings, "disk.space", "Free disk space", free_status,
            f"{_human_bytes(free)} free of {_human_bytes(usage.total)}",
            None if free_status == "ok" else "pkg clean   # or remove old build outputs",
            {"free_bytes": free, "total_bytes": usage.total},
        )
    except OSError as exc:
        _finding(checks, timings, "disk.space", "Free disk space", "warning",
                 f"unavailable: {exc}", "Check that the install location still exists")

    home = get_home()
    mount = get_mount_info(str(app_dir if app_dir.exists() else home))
    noexec = "noexec" in (mount.get("options", "").split(","))
    on_shared = str(app_dir).startswith("/storage/") or str(home).startswith("/storage/")
    if noexec or on_shared:
        _finding(
            checks, timings, "environment.storage", "Executable storage", "warning",
            ("noexec mount at " if noexec else "shared storage at ") + str(mount.get("mountpoint") or home),
            "Install Wobble under $HOME (Termux private storage), never under /storage/emulated",
            {"mount": mount, "shared": on_shared},
        )
    else:
        _finding(checks, timings, "environment.storage", "Executable storage", "ok",
                 f"{mount.get('fstype') or 'unknown'} at {mount.get('mountpoint') or home}",
                 None, {"mount": mount})

    # Interrupted-install leftovers
    leftovers = [str(p) for pattern in (".app.tmp-*", ".app.old")
                 for p in root.glob(pattern)]
    _finding(
        checks, timings, "installer.leftovers", "Interrupted install debris",
        "ok" if not leftovers else "warning",
        "none" if not leftovers else f"{len(leftovers)} leftover path(s)",
        None if not leftovers else "wob self repair   # removes staging dirs and backups",
        {"paths": leftovers[:10]},
    )

    # -- history -----------------------------------------------------
    _add_history_check(checks, timings)

    # -- deep verification ------------------------------------------
    if deep:
        t0 = time.monotonic()
        verification = installer.verify(root)
        verify_status = "ok" if verification.get("ok") else "critical"
        if verification.get("ok"):
            detail = f"{verification['checked']} files, SHA-256 verified"
        else:
            detail = (f"{len(verification.get('missing', []))} missing, "
                      f"{len(verification.get('modified', []))} modified, "
                      f"{len(verification.get('unreadable', []))} unreadable")
            if verification.get("error"):
                detail = verification["error"]
        _finding(
            checks, timings, "integrity.hashes", "File integrity (SHA-256)", verify_status,
            detail,
            None if verify_status == "ok" else "wob self install   # reinstall a verified runtime",
            {k: verification.get(k) for k in
             ("checked", "file_count", "missing", "modified", "unreadable",
              "launcher_ok", "elapsed_ms", "hashed_bytes")},
        )
        timings["integrity.hashes"] = round((time.monotonic() - t0) * 1000, 2)

        t0 = time.monotonic()
        smoke = _smoke_imports()
        _finding(
            checks, timings, "runtime.imports", "Module smoke test",
            "ok" if smoke["ok"] else "critical",
            f"{smoke['loaded']}/{smoke['total']} core modules import cleanly"
            if smoke["ok"] else
            "failed: " + ", ".join(item["module"] for item in smoke["failed"]),
            None if smoke["ok"] else "wob self install   # corrupt bytecode or source; reinstall",
            smoke,
        )
        timings["runtime.imports"] = round((time.monotonic() - t0) * 1000, 2)

    report = _finish_report(
        checks, timings, started, mode=mode, root=root, bin_path=bin_path,
        app_dir=app_dir, manifest=manifest, deep=deep, python=python,
    )
    report["path"] = {
        "bin_dir": str(bin_path),
        "in_path": path_info["in_path"],
        "which": path_info["which"],
        "shadowed": path_info["shadowed"],
    }
    report["source"] = {
        "path": manifest.get("source"),
        "exists": bool(manifest.get("source") and Path(manifest["source"]).exists()),
    }
    return report


def _finish_report(checks: list, timings: dict, started: float, mode: str, root: Path,
                   bin_path: Path, app_dir, manifest, deep: bool, python: dict) -> dict:
    """Assemble counts, status, issues, and next steps from findings."""
    counts = {"ok": 0, "info": 0, "warning": 0, "critical": 0}
    score_total = 0.0
    for finding in checks:
        counts[finding.status] = counts.get(finding.status, 0) + 1
        score_total += 0.0 if finding.status == "critical" else (
            0.55 if finding.status == "warning" else 1.0)

    bad = [f for f in checks if f.status in _BAD]
    critical = [f for f in checks if f.status == "critical"]
    if critical:
        status = "broken"
    elif bad:
        status = "degraded"
    else:
        status = "healthy"

    score = 0 if not checks else int(round(100 * score_total / len(checks)))
    if critical:
        score = min(score, 40)

    next_steps = []
    for finding in bad:
        if finding.fix and finding.fix not in next_steps:
            next_steps.append(finding.fix)

    elapsed_ms = round((time.monotonic() - started) * 1000, 1)
    summary = _manifest_summary(manifest) if manifest else {}
    standalone = mode == "standalone"
    launcher = next((f for f in checks if f.code == "launcher.present"), None)
    return {
        "status": status,
        "ok": not bad,
        # Compatibility keys: the pre-1.3 `self status` document and its tests
        # assert on these names, and agents may already depend on them.
        "installed": standalone,
        "standalone": standalone,
        "healthy": standalone and status != "broken",
        "launcher": (launcher.data.get("path") if launcher and launcher.status != "critical"
                     else None),
        "source": (manifest.get("source") if manifest else str(installer.package_root())),
        "source_exists": (bool(manifest.get("source") and Path(manifest["source"]).exists())
                          if manifest else True),
        "completions": summary.get("completions", []),
        "mode": mode,
        "install_root": str(root),
        "bin_dir": str(bin_path),
        "app_dir": str(app_dir) if app_dir else None,
        "manifest": str(installer.manifest_path(root)) if manifest else None,
        "version": __version__,
        "manifest_version": summary.get("version"),
        "installed_at": summary.get("installed_at"),
        "file_count": summary.get("file_count", 0),
        "total_bytes": summary.get("total_bytes", 0),
        "python": python,
        "termux": is_termux(),
        "deep": deep,
        "score": score,
        "counts": counts,
        "checks": [f.to_dict() for f in checks],
        "issues": [f.to_dict() for f in bad],
        "next_steps": next_steps,
        "incidents": health.incident_summary(limit=5),
        "timings": timings,
        "elapsed_ms": elapsed_ms,
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------
def exit_code(report: dict, strict: bool = False) -> int:
    """0 when healthy; 1 when broken (or degraded with ``strict``)."""
    if report.get("status") == "broken":
        return 1
    if strict and report.get("status") == "degraded":
        return 1
    return 0


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def render(report: dict, use_color: bool = True, width: int = 66) -> str:
    """Render a human-readable report: grouped findings, meter, and next steps."""
    from wobble.core import theme

    def paint(text: str, *styles: str) -> str:
        return theme.paint(text, *styles, enabled=use_color)

    lines = []
    mode = report.get("mode")
    version = report.get("version")
    installed_at = report.get("installed_at")
    head = f"{mode}  v{version}"
    if installed_at:
        head += f"  installed {installed_at}"
    overall = "ok" if report.get("ok") else (
        "error" if report.get("status") == "broken" else "warning")
    lines.append(theme.rule("wobble self status", width=width, use_color=use_color))
    lines.append(f"  {theme.badge(overall, use_color)} {head}")
    if report.get("app_dir"):
        home = str(get_home())
        app = report["app_dir"]
        if home and app.startswith(home):
            app = "~" + app[len(home):]
        lines.append(f"         {paint('app', theme.DIM)} {app}")

    groups = {}
    for check in report.get("checks", []):
        if check["status"] == "ok":
            continue
        groups.setdefault(check["status"], []).append(check)

    if not groups:
        lines.append(f"  {theme.badge('ok', use_color)} "
                     f"all {len(report.get('checks', []))} checks passed")
    for status in ("critical", "warning", "info"):
        for check in groups.get(status, []):
            lines.append(f"  {theme.badge(status, use_color)} {check['title']:<24} {check['detail']}")
            if check.get("fix"):
                lines.append("        " + paint("fix:", theme.CYAN) + " " + check["fix"])

    counts = report.get("counts", {})
    score = report.get("score", 0)
    summary_rows = [
        f"{theme.progress_bar(score, width=22, use_color=use_color, invert=True)}  "
        f"{report.get('status')}",
        f"{theme.badge('ok', use_color)} passed {counts.get('ok', 0)}   "
        f"{theme.badge('warning', use_color)} warnings {counts.get('warning', 0)}   "
        f"{theme.badge('error', use_color)} critical {counts.get('critical', 0)}",
        f"{paint('scan', theme.DIM)}     {report.get('elapsed_ms')} ms"
        + ("  (deep)" if report.get("deep") else "  (fast: metadata only)"),
    ]
    if report.get("incidents", {}).get("total"):
        incidents = report["incidents"]
        summary_rows.append(
            f"{paint('history', theme.DIM)}  {incidents['total']} incident(s), "
            f"last {incidents.get('last_age')} ago")
    lines.append("")
    lines.append(theme.box("summary", summary_rows, width=width, use_color=use_color))

    if report.get("next_steps"):
        lines.append("")
        lines.append(paint("  next steps:", theme.BOLD, theme.YELLOW))
        for step in report["next_steps"]:
            lines.append("    " + theme.list_item(step, use_color=use_color))

    if report.get("deep") and report.get("status") != "broken":
        lines.append("")
        lines.append(paint("  deep check: hashes verified, core modules import cleanly.",
                           theme.DIM))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Repair
# ---------------------------------------------------------------------------
def repair(install_root: Path = None, bin_dir: Path = None, compile_bytecode: bool = True,
           completions: bool = True, update_path: bool = False,
           fix_config: bool = True, accept_current: bool = False) -> dict:
    """Fix everything that can be fixed without weakening integrity.

    Missing or modified *runtime* files are never papered over: the honest fix
    for a damaged runtime is a reinstall, and this function says so instead of
    silently rewriting hashes. ``accept_current=True`` is the explicit opt-in for
    "I patched my install on purpose, re-baseline it".
    """
    started = time.monotonic()
    root = Path(install_root).expanduser().resolve() if install_root else installer.default_install_root()
    bin_path = Path(bin_dir).expanduser().resolve() if bin_dir else installer.default_bin_dir()
    manifest = installer.read_manifest(root)
    actions, failed, skipped = [], [], []

    if not manifest:
        return {
            "success": False,
            "error": "No install manifest found; there is nothing to repair.",
            "error_code": "installation_manifest_missing",
            "fix": "wob self install   (or: sh install.sh)",
            "install_root": str(root),
            "actions": [],
            "failed": [],
            "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
        }

    app_dir = Path(manifest.get("app_dir", root / installer.APP_DIRNAME))
    if not app_dir.is_dir() or not (app_dir / "wob.py").is_file():
        return {
            "success": False,
            "error": "The installed runtime is missing; only a reinstall can restore it.",
            "error_code": "installation_runtime_missing",
            "fix": "wob self install   (or: sh install.sh)",
            "install_root": str(root),
            "app_dir": str(app_dir),
            "actions": [],
            "failed": [str(app_dir)],
            "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
        }

    # 1. Interrupted-install debris
    try:
        removed = installer.cleanup_leftovers(root)
        if removed:
            actions.append({"action": "cleanup_leftovers", "removed": removed})
    except OSError as exc:
        failed.append({"action": "cleanup_leftovers", "error": str(exc)})

    # 2. Launchers (missing, stale target, wrong permissions)
    try:
        launcher_result = installer.rewrite_launchers(
            app_dir,
            bin_dir=bin_path,
            launchers=manifest.get("launchers") or [],
        )
        if launcher_result["written"]:
            actions.append({"action": "rewrite_launchers", **launcher_result})
        if launcher_result["skipped"]:
            skipped.append({"action": "rewrite_launchers",
                            "reason": "not written by Wobble", "paths": launcher_result["skipped"]})
    except OSError as exc:
        failed.append({"action": "rewrite_launchers", "error": str(exc)})

    # 3. Bytecode cache
    if compile_bytecode:
        missing, _total = _pyc_coverage(app_dir)
        if missing:
            result = installer.compile_runtime(app_dir)
            actions.append({"action": "compile_bytecode", **result})
            if not result["ok"]:
                failed.append({"action": "compile_bytecode", "error": "no bytecode produced"})

    # 4. Completions
    if completions:
        try:
            written = installer.install_completions(root)
            if written:
                actions.append({"action": "install_completions", "written": written})
        except OSError as exc:
            failed.append({"action": "install_completions", "error": str(exc)})

    # 5. Corrupt config / registry (backup first, never overwrite blindly)
    if fix_config:
        for label, path in (("config", config_path()), ("registry", registry_path())):
            _data, error = _read_json(path)
            if not error:
                continue
            try:
                backup = backup_corrupted_file(path)
                actions.append({"action": f"backup_corrupt_{label}",
                                "path": str(path), "backup": str(backup)})
            except OSError as exc:
                failed.append({"action": f"backup_corrupt_{label}", "error": str(exc)})

    # 6. PATH
    if update_path:
        try:
            touched = installer.update_shell_path(bin_path)
            actions.append({"action": "update_shell_path", "touched": touched})
        except OSError as exc:
            failed.append({"action": "update_shell_path", "error": str(exc)})

    # 7. Explicit re-baseline after a deliberate local patch
    if accept_current:
        try:
            refreshed = installer.refresh_manifest(root)
            actions.append({"action": "refresh_manifest", **refreshed})
        except Exception as exc:  # InstallerError or OSError
            failed.append({"action": "refresh_manifest", "error": str(exc)})

    verification = installer.verify(root)
    unresolved = []
    if verification.get("missing"):
        unresolved.append({"problem": "missing runtime files", "files": verification["missing"][:20],
                           "fix": "wob self install"})
    if verification.get("modified"):
        unresolved.append({"problem": "modified runtime files", "files": verification["modified"][:20],
                           "fix": "wob self install   (or: wob self repair --accept-current)"})
    if not verification.get("launcher_ok"):
        unresolved.append({"problem": "launcher still invalid", "fix": "wob self install --force"})

    ok = not failed and not unresolved
    return {
        "success": ok,
        "repaired": bool(actions),
        "install_root": str(root),
        "app_dir": str(app_dir),
        "actions": actions,
        "failed": failed,
        "skipped": skipped,
        "unresolved": unresolved,
        "verification": verification,
        "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
    }
