"""Wobble Environment Doctor
Inspects system architecture, Android version, Termux setup, SDK, JDK, web
tools, and the health of the Wobble installation itself.

Three things make this fast and useful on a phone:

1. **Concurrent probes.** Tool version checks run in a small thread pool; process
   creation, not CPU, is the bottleneck on Android.
2. **Self-invalidating cache.** Probe results are stored in ``~/.wobble/cache``
   keyed by the executable's inode fingerprint, so a second ``wob doctor`` costs
   almost nothing while an upgraded tool invalidates itself automatically.
3. **Memory of the last run.** Each run is diffed against the previous snapshot,
   so a check that *just* broke is reported as a regression instead of blending
   into the noise, and a check that has failed for days is labelled persistent.

Every failed check still ships with a copy-paste fix.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path

from wobble.core import health, packages, probecache, theme
from wobble.core.context import (
    find_tool,
    get_android_sdk_candidates,
    get_android_version,
    get_architecture,
    get_home,
    get_java_home_candidates,
    get_lan_ip,
    get_memory_info,
    get_mount_info,
    get_path_entries,
    get_prefix,
    get_python_info,
    get_storage_info,
    get_termux_version,
    is_shared_storage,
    is_termux,
)
from wobble.core.executor import run_command
from wobble.core.logger import get_logger

CATEGORIES = (
    "System",
    "Resources",
    "Environment",
    "Dev Tools",
    "Web Tools",
    "Android Toolchain",
    "Wobble Runtime",
)
CATEGORY_ALIASES = {
    "system": "System",
    "resources": "Resources",
    "env": "Environment",
    "environment": "Environment",
    "dev": "Dev Tools",
    "tools": "Dev Tools",
    "web": "Web Tools",
    "android": "Android Toolchain",
    "sdk": "Android Toolchain",
    "wobble": "Wobble Runtime",
    "self": "Wobble Runtime",
}
FAIL_ON_RANK = {"never": 99, "error": 3, "missing": 2, "warning": 1}


class CheckResult:
    """One diagnostic row."""

    __slots__ = ("name", "category", "status", "details", "problem", "fix", "code", "cached")

    def __init__(
        self,
        name: str,
        category: str,
        status: str,  # "ok", "warning", "missing", "error"
        details: str = "",
        problem: Optional[str] = None,
        fix: Optional[str] = None,
        code: Optional[str] = None,
        cached: bool = False,
    ):
        self.name = name
        self.category = category
        self.status = status
        self.details = details
        self.problem = problem
        self.fix = fix
        self.code = code or re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        self.cached = cached

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "code": self.code,
            "category": self.category,
            "status": self.status,
            "details": self.details,
            "problem": self.problem,
            "fix": self.fix,
        }


# ---------------------------------------------------------------------------
# Probing
# ---------------------------------------------------------------------------
def check_tool_version(cmd: List[str], version_flag: str = "--version",
                       timeout: int = 5) -> Tuple[bool, str]:
    """Run a tool and extract its first useful version line."""
    try:
        res = run_command([cmd[0], version_flag], timeout=timeout)
        out = (res.stdout or "").strip()
        err = (res.stderr or "").strip()
        if res.success:
            first_line = (out or err).splitlines()[0]
            return True, first_line
        # Several tools (java, some gcc builds) print their version to stderr
        # and/or exit non-zero.
        combined = out or err
        if combined:
            return True, combined.splitlines()[0]
    except Exception:
        pass
    return False, ""


def _probe_version(binary: str, flag: str, refresh: bool = False) -> Tuple[bool, str, bool]:
    """Return ``(ok, version_line, from_cache)`` for one tool."""
    key = f"{binary}\x00{flag}"
    fingerprint = probecache.fingerprint(binary)
    if not refresh:
        hit, value = probecache.get(key, fingerprint)
        if hit and isinstance(value, list) and len(value) == 2:
            return bool(value[0]), str(value[1]), True
    ok, line = check_tool_version([binary], flag)
    if ok or os.path.exists(binary):
        probecache.put(key, [ok, line], fingerprint)
    return ok, line, False


def check_tools_parallel(checks: Dict[str, Tuple[Optional[str], str]],
                         refresh: bool = False) -> Dict[str, Tuple[bool, str]]:
    """Probe multiple tools concurrently and cache the answers.

    Returns ``{label: (ok, version_line)}``. Cache hits skip the subprocess
    entirely, which is what makes a warm ``wob doctor`` cheap.
    """
    results: Dict[str, Tuple[bool, str]] = {}
    runnable = {label: spec for label, spec in checks.items() if spec[0]}
    sources: Dict[str, bool] = {}

    if runnable:
        from concurrent.futures import ThreadPoolExecutor

        workers = min(8, len(runnable))
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = {
                label: pool.submit(_probe_version, spec[0], spec[1], refresh)
                for label, spec in runnable.items()
            }
            for label, future in futures.items():
                try:
                    ok, line, cached = future.result(timeout=20)
                    results[label] = (ok, line)
                    sources[label] = cached
                except Exception:
                    results[label] = (False, "")
                    sources[label] = False

    for label in checks:
        results.setdefault(label, (False, ""))
        sources.setdefault(label, False)

    check_tools_parallel.last_sources = sources
    return results


check_tools_parallel.last_sources = {}  # type: ignore[attr-defined]


def _major_version(text: str) -> Optional[int]:
    """Extract the first plausible major version number from a tool banner."""
    match = re.search(r"(\d+)(?:\.\d+)*(?:[-_a-zA-Z]|$)", text or "")
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _gradle_version(text: str) -> Optional[Tuple[int, int]]:
    match = re.search(r"Gradle\s+(\d+)\.(\d+)", text or "")
    if match:
        return int(match.group(1)), int(match.group(2))
    match = re.search(r"(\d+)\.(\d+)", text or "")
    if match:
        return int(match.group(1)), int(match.group(2))
    return None


# ---------------------------------------------------------------------------
# Category helpers
# ---------------------------------------------------------------------------
def resolve_categories(only: Optional[str]) -> Optional[List[str]]:
    """Turn ``--only system,android`` into canonical category names."""
    if not only:
        return None
    wanted: List[str] = []
    unknown: List[str] = []
    for raw in str(only).replace(";", ",").split(","):
        token = raw.strip().lower()
        if not token:
            continue
        if token in CATEGORY_ALIASES:
            category = CATEGORY_ALIASES[token]
        else:
            match = [c for c in CATEGORIES if c.lower() == token]
            if not match:
                unknown.append(raw.strip())
                continue
            category = match[0]
        if category not in wanted:
            wanted.append(category)
    if unknown:
        raise ValueError(
            f"Unknown category: {', '.join(unknown)}. "
            f"Choose from: {', '.join(sorted(CATEGORY_ALIASES))}"
        )
    return wanted or None


# ---------------------------------------------------------------------------
# Individual probes
# ---------------------------------------------------------------------------
def _wobble_runtime_checks() -> List[CheckResult]:
    """Fold the self-check engine into the doctor under its own category."""
    from wobble.core import selfcheck

    report = selfcheck.inspect()
    results: List[CheckResult] = []
    issues = [c for c in report.get("checks", []) if c["status"] in ("warning", "critical")]
    for check in issues[:8]:
        results.append(CheckResult(
            name=check["title"],
            category="Wobble Runtime",
            status="error" if check["status"] == "critical" else "warning",
            details=check["detail"],
            problem=check["detail"] if check["status"] == "critical" else None,
            fix=check.get("fix"),
            code=check["code"],
        ))
    if not issues:
        results.append(CheckResult(
            name="Wobble Installation",
            category="Wobble Runtime",
            status="ok",
            details=f"{report.get('mode')} v{report.get('version')} "
                    f"({report.get('file_count')} files, {report.get('elapsed_ms')} ms self-check)",
            code="wobble_installation",
        ))
    return results


def _path_checks() -> List[CheckResult]:
    """Detect dead and duplicated PATH entries."""
    entries = get_path_entries()
    seen = set()
    dead: List[str] = []
    duplicates: List[str] = []
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
    if not dead:
        detail = f"{len(entries)} valid entries"
        if duplicates:
            detail += f" ({len(duplicates)} duplicate path)"
        return [CheckResult(
            name="PATH Entries", category="Environment", status="ok",
            details=detail, code="path_entries",
        )]
    bits = [f"{len(dead)} missing"]
    if duplicates:
        bits.append(f"{len(duplicates)} duplicate")
    return [CheckResult(
        name="PATH Entries", category="Environment", status="warning",
        details=", ".join(bits) + f" of {len(entries)} entries",
        problem="Dead PATH entries slow command lookups and hide missing installs: "
                + ", ".join((dead + duplicates)[:4]),
        fix="Remove the stale entries from PATH in ~/.bashrc and open a new shell.",
        code="path_entries",
    )]


def _storage_mount_check() -> Optional[CheckResult]:
    """Warn when the home directory lives on noexec/shared storage."""
    home = get_home()
    mount = get_mount_info(str(home))
    options = (mount.get("options") or "").split(",")
    if "noexec" in options or is_shared_storage(home):
        return CheckResult(
            name="Executable Home", category="Environment", status="warning",
            details=f"{mount.get('fstype') or 'unknown'} at {mount.get('mountpoint') or home}"
                    + (" (noexec)" if "noexec" in options else " (shared storage)"),
            problem="Binaries cannot execute from shared storage, and Android enforces W^X "
                    "inside app data directories.",
            fix="Keep Wobble and projects under Termux's private $HOME, not /storage/emulated.",
            code="executable_home",
        )
    return None


def _storage_fix() -> str:
    """Platform-appropriate "free up space" advice."""
    if packages.package_family() == packages.TERMUX:
        return "Run 'wob clean --all' and 'pkg clean', or remove old build outputs."
    return ("Run 'wob clean --all', clear your package manager's cache, or remove "
            "old build outputs.")


def _package_manager_check() -> CheckResult:
    """Termux ships ``pkg``; other systems use apt/dnf/pacman."""
    pkg = find_tool("pkg")
    if pkg:
        return CheckResult(name="Package Manager", category="Environment", status="ok",
                           details=pkg, code="package_manager")
    for name in ("apt", "apt-get", "dnf", "pacman", "apk"):
        found = find_tool(name)
        if found:
            return CheckResult(name="Package Manager", category="Environment", status="ok",
                               details=found, code="package_manager")
    return CheckResult(
        name="Package Manager", category="Environment", status="warning",
        details="No supported package manager found",
        problem="No supported package manager was found, so install hints cannot be resolved.",
        fix="Install Termux from F-Droid or GitHub Releases (pkg ships with its bootstrap); "
            "otherwise install apt, dnf, pacman or apk and re-run 'wob doctor'.",
        code="package_manager",
    )


def _termux_channel_check(in_termux: bool, termux_version: Optional[str]) -> CheckResult:
    """Play Store builds of Termux are deprecated and usually outdated."""
    if not in_termux:
        return CheckResult(
            name="Termux Channel", category="System", status="ok",
            details="Not running in Termux", code="termux_channel",
        )
    package = os.environ.get("TERMUX_APP__PACKAGE_NAME", "")
    version_name = os.environ.get("TERMUX_APP__VERSION_NAME", "") or (termux_version or "")
    haystack = f"{package} {version_name} {termux_version or ''}".lower()
    if "play" in haystack:
        return CheckResult(
            name="Termux Channel", category="System", status="warning",
            details="Play Store build detected",
            problem="Play Store builds are deprecated and cannot be updated.",
            fix="Reinstall Termux from F-Droid or GitHub Releases.",
            code="termux_channel",
        )
    return CheckResult(
        name="Termux Channel", category="System", status="ok",
        details=version_name or "F-Droid/GitHub build (assumed)", code="termux_channel",
    )


def _sdk_details(sdk_path: Path) -> Dict[str, Any]:
    """Inspect an Android SDK layout (cheap directory listings)."""
    info: Dict[str, Any] = {
        "path": str(sdk_path),
        "platforms": [],
        "build_tools": [],
        "cmdline_tools": (sdk_path / "cmdline-tools").is_dir(),
        "platform_tools": (sdk_path / "platform-tools").is_dir(),
    }
    for name, key in (("platforms", "platforms"), ("build-tools", "build_tools")):
        directory = sdk_path / name
        try:
            if directory.is_dir():
                info[key] = sorted(child.name for child in directory.iterdir() if child.is_dir())
        except OSError:
            pass
    return info


def _jdk_major(text: str) -> Optional[int]:
    """Parse Java's version from ``java -version`` output ('17.0.9' or '1.8.0_392')."""
    match = re.search(r'version "(\d+)(?:\.(\d+))?', text or "")
    if not match:
        return _major_version(text)
    major = int(match.group(1))
    if major == 1 and match.group(2):
        return int(match.group(2))
    return major


def _empty_check(name: str, category: str, details: str, code: str) -> CheckResult:
    return CheckResult(name=name, category=category, status="missing",
                       details=details, code=code)


# ---------------------------------------------------------------------------
# Full inspection
# ---------------------------------------------------------------------------
def inspect_environment(quick: bool = False, only: Optional[str] = None,
                        refresh: bool = False, include_self: bool = True) -> List[CheckResult]:
    """Run all diagnostic checks across the system.

    ``quick`` skips subprocess version probes and reports resolved paths instead.
    ``only`` filters categories. ``refresh`` ignores the disk probe cache.
    """
    started = time.monotonic()
    selected = resolve_categories(only)
    results: List[CheckResult] = []

    def wanted(category: str) -> bool:
        return selected is None or category in selected

    # -- System -------------------------------------------------------
    if wanted("System"):
        arch = get_architecture()
        known_arch = arch in ("aarch64", "arm", "x86_64", "x86")
        results.append(CheckResult(
            name="CPU Architecture", category="System",
            status="ok" if known_arch else "warning",
            details=f"{arch} ({os.uname().machine})",
            problem=None if known_arch else f"Uncommon architecture: {arch}",
            fix=None if known_arch else
            "Termux development works best on aarch64 (ARM64); some binaries may need compiling.",
            code="cpu_architecture",
        ))

        in_termux = is_termux()
        results.append(CheckResult(
            name="Termux Environment", category="System",
            status="ok" if in_termux else "warning",
            details=f"Prefix: {get_prefix()}" if in_termux else "Running outside standard Termux",
            problem=None if in_termux else "Not detected as running inside Termux.",
            fix=None if in_termux else "Ensure $PREFIX is set or run directly inside the Termux app.",
            code="termux_environment",
        ))

        termux_version = get_termux_version()
        results.append(CheckResult(
            name="Termux Version", category="System",
            status="ok" if termux_version else "warning",
            details=termux_version or "Could not detect exact version",
            problem=None if termux_version else "Termux version string not found in environment or dpkg.",
            fix=None if termux_version else
            "Use F-Droid or GitHub Releases — the Play Store build is deprecated.",
            code="termux_version",
        ))
        results.append(_termux_channel_check(in_termux, termux_version))

        android_info = get_android_version()
        release = android_info.get("release")
        api = android_info.get("api_level")
        device = f"{android_info.get('brand', '')} {android_info.get('model', '')}".strip()
        if release:
            details = f"Android {release} (API {api or 'unknown'})"
            if device:
                details += f" - {device}"
            results.append(CheckResult(
                name="Android Version", category="System", status="ok",
                details=details, code="android_version",
            ))
        else:
            results.append(CheckResult(
                name="Android Version", category="System", status="warning",
                details="Could not query Android getprop",
                problem="Android system properties are not accessible.",
                fix="Usually harmless inside a proot/container, but on-device builds need them.",
                code="android_version",
            ))

        python = get_python_info()
        py_ok = tuple(python["version_info"][:2]) >= (3, 8)
        results.append(CheckResult(
            name="Python Runtime", category="System",
            status="ok" if py_ok else "error",
            details=f"{python['implementation']} {python['version']} at {python['executable']}",
            problem=None if py_ok else "Wobble requires Python 3.8 or newer.",
            fix=None if py_ok else packages.install_hint(
                ("python",), "Upgrade Python with: "),
            code="python_runtime",
        ))

    # -- Resources ----------------------------------------------------
    if wanted("Resources"):
        storage = get_storage_info()
        if "error" not in storage:
            free_bytes = storage.get("free_bytes", 0)
            low_storage = free_bytes < (1.5 * 1024 * 1024 * 1024)
            results.append(CheckResult(
                name="Available Storage", category="Resources",
                status="warning" if low_storage else "ok",
                details=f"{storage['free_human']} free of {storage['total_human']} "
                        f"({storage['percent_used']}% used)",
                problem="Low disk space: Gradle builds and the Android SDK need gigabytes."
                if low_storage else None,
                fix=_storage_fix() if low_storage else None,
                code="available_storage",
            ))
        else:
            results.append(CheckResult(
                name="Available Storage", category="Resources", status="warning",
                details=storage.get("error", "unavailable"),
                problem="Could not read filesystem statistics for the home directory.",
                fix="Check that $HOME exists and is readable.",
                code="available_storage",
            ))

        mem = get_memory_info()
        if "error" not in mem:
            avail_bytes = mem.get("available_bytes", 0)
            low_mem = avail_bytes < (500 * 1024 * 1024)
            results.append(CheckResult(
                name="System Memory", category="Resources",
                status="warning" if low_mem else "ok",
                details=f"{mem['available_human']} available of {mem['total_human']}",
                problem="Low available RAM; heavy Gradle or Node builds may be killed by the OOM killer."
                if low_mem else None,
                fix="Close background apps or enable zram/swap if the device supports it."
                if low_mem else None,
                code="system_memory",
            ))
        else:
            results.append(CheckResult(
                name="System Memory", category="Resources", status="warning",
                details="Unavailable", problem="/proc/meminfo is not readable.",
                fix="Harmless in some containers; on-device builds need it.",
                code="system_memory",
            ))

    # -- Environment --------------------------------------------------
    if wanted("Environment"):
        prefix_bin = str(get_prefix() / "bin")
        home_local_bin = str(get_home() / ".local" / "bin")
        path_env = os.environ.get("PATH", "")
        path_ok = prefix_bin in path_env.split(os.pathsep)
        results.append(CheckResult(
            name="PATH Configuration", category="Environment",
            status="ok" if path_ok else "warning",
            details="Standard PATH active" if path_ok else f"Missing {prefix_bin} in PATH",
            problem=f"{prefix_bin} is not in PATH." if not path_ok else None,
            fix=f'Add export PATH="{prefix_bin}:{home_local_bin}:$PATH" to ~/.bashrc'
            if not path_ok else None,
            code="path_configuration",
        ))
        results.extend(_path_checks())

        storage_dir = get_home() / "storage"
        results.append(CheckResult(
            name="Android Storage Access", category="Environment",
            status="ok" if storage_dir.exists() else "warning",
            details="Access granted (~/storage exists)" if storage_dir.exists() else "Not set up",
            problem="Termux storage permission is missing; exporting APKs to Download will fail."
            if not storage_dir.exists() else None,
            fix="Run 'termux-setup-storage' in Termux and grant permission."
            if not storage_dir.exists() else None,
            code="android_storage_access",
        ))
        mount_check = _storage_mount_check()
        if mount_check:
            results.append(mount_check)
        results.append(_package_manager_check())

    # -- Resolve binaries (cheap PATH lookups) ------------------------
    binaries = {
        "git": find_tool("git"),
        "python": find_tool("python3") or find_tool("python"),
        "node": find_tool("node"),
        "npm": find_tool("npm"),
        "php": find_tool("php"),
        "java": find_tool("java"),
        "javac": find_tool("javac"),
        "gradle": find_tool("gradle"),
        "adb": find_tool("adb"),
    }
    javac_bin = binaries["javac"]
    aapt2_bin = find_tool("aapt2") or find_tool("aapt")
    apksigner_bin = find_tool("apksigner")
    zipalign_bin = find_tool("zipalign")

    flags = {
        "git": "--version",
        "python": "--version",
        "node": "--version",
        "npm": "--version",
        "php": "--version",
        "java": "-version",
        "gradle": "--version",
        "adb": "version",
    }
    # A filtered run must not pay for probes belonging to categories the user
    # excluded: `wob doctor --only wobble` should not spawn eight version checks.
    needed = set()
    if wanted("Dev Tools"):
        needed.update(("git", "python"))
    if wanted("Web Tools"):
        needed.update(("node", "npm", "php"))
    if wanted("Android Toolchain"):
        needed.update(("java", "gradle", "adb"))

    probe_started = time.monotonic()
    if quick:
        versions = {label: (bool(path), path or "") for label, path in binaries.items()}
    else:
        versions = check_tools_parallel(
            {label: (binaries[label], flags[label]) for label in needed if binaries[label]},
            refresh=refresh,
        )
    probe_ms = round((time.monotonic() - probe_started) * 1000, 1)
    cache_sources = getattr(check_tools_parallel, "last_sources", {})

    def cached_flag(label: str) -> bool:
        return bool(cache_sources.get(label))

    def version_of(label: str):
        return versions.get(label, (False, ""))

    # -- Dev Tools ----------------------------------------------------
    if wanted("Dev Tools"):
        if binaries["git"]:
            ok, version = version_of("git")
            results.append(CheckResult(
                name="Git", category="Dev Tools",
                status="ok" if ok else "warning",
                details=version or binaries["git"],
                problem=None if ok else "Git was found but did not report a version.",
                fix=None if ok else packages.install_hint(("git",), "Install Git with: "),
                code="git", cached=cached_flag("git"),
            ))
        else:
            results.append(_empty_check(
                "Git", "Dev Tools", "Not installed", "git"))
            results[-1].problem = "Git is needed for templates, plugins, and version control."
            results[-1].fix = packages.install_hint(("git",), "Install Git with: ")

        if binaries["python"]:
            ok, version = version_of("python")
            results.append(CheckResult(
                name="Python", category="Dev Tools", status="ok",
                details=version or binaries["python"], code="python",
                cached=cached_flag("python"),
            ))
        else:
            results.append(CheckResult(
                name="Python", category="Dev Tools", status="missing",
                details="Not installed",
                problem="Python 3 runs Wobble itself and Python web projects.",
                fix=packages.install_hint(("python",), "Install Python with: "),
                code="python",
            ))

    # -- Web Tools ----------------------------------------------------
    if wanted("Web Tools"):
        if binaries["node"]:
            ok, version = version_of("node")
            results.append(CheckResult(
                name="Node.js", category="Web Tools", status="ok",
                details=version or binaries["node"], code="nodejs",
                cached=cached_flag("node"),
            ))
        else:
            results.append(CheckResult(
                name="Node.js", category="Web Tools", status="missing",
                details="Not installed",
                problem="Node.js is required for Vite, React, Vue, Svelte, and Next.js.",
                fix=packages.install_hint(("nodejs",), "Install Node.js with: "),
                code="nodejs",
            ))

        if binaries["npm"]:
            ok, version = version_of("npm")
            results.append(CheckResult(
                name="npm", category="Web Tools", status="ok",
                details=version or binaries["npm"], code="npm",
                cached=cached_flag("npm"),
            ))
        else:
            results.append(CheckResult(
                name="npm", category="Web Tools",
                status="warning" if binaries["node"] else "missing",
                details="Not installed",
                problem="npm installs web project dependencies.",
                fix=packages.install_hint(("nodejs",), "Install npm (bundled with nodejs): "),
                code="npm",
            ))

        if binaries["php"]:
            ok, version = version_of("php")
            results.append(CheckResult(
                name="PHP", category="Web Tools", status="ok",
                details=(version.splitlines()[0] if version else binaries["php"]),
                code="php", cached=cached_flag("php"),
            ))
        else:
            results.append(CheckResult(
                name="PHP", category="Web Tools", status="missing",
                details="Not installed (optional)",
                problem="PHP is only needed for PHP web applications and APIs.",
                fix=packages.install_hint(("php",), "Install PHP with: "),
                code="php",
            ))

    # -- Android Toolchain -------------------------------------------
    if wanted("Android Toolchain"):
        if binaries["java"]:
            ok, version = version_of("java")
            jdk_major = _jdk_major(version)
            details = version or binaries["java"]
            if javac_bin:
                details += " (JDK compiler present)"
            results.append(CheckResult(
                name="Java / JDK", category="Android Toolchain",
                status="ok" if javac_bin else "warning",
                details=details,
                problem=None if javac_bin else "Java runtime found, but javac is missing.",
                fix=None if javac_bin else packages.install_hint(
                    ("jdk",), "Install the full JDK: "),
                code="java_jdk", cached=cached_flag("java"),
            ))
            java_home = os.environ.get("JAVA_HOME")
            if java_home and not Path(java_home).is_dir():
                results.append(CheckResult(
                    name="JAVA_HOME", category="Android Toolchain", status="warning",
                    details=f"{java_home} does not exist",
                    problem="JAVA_HOME points at a missing directory; Gradle will fail to start.",
                    fix="Unset JAVA_HOME or point it at a real JDK ("
                        + (packages.install_command(("jdk",)) or "install a JDK") + ").",
                    code="java_home",
                ))
            elif not java_home:
                candidates = get_java_home_candidates()
                results.append(CheckResult(
                    name="JAVA_HOME", category="Android Toolchain", status="ok",
                    details=str(candidates[0]) if candidates else "unset (java is on PATH)",
                    code="java_home",
                ))
        else:
            results.append(CheckResult(
                name="Java / JDK", category="Android Toolchain", status="missing",
                details="Not installed",
                problem="A JDK is required to build Android APKs with Gradle.",
                fix=packages.install_hint(("jdk",), "Install OpenJDK 17 with: "),
                code="java_jdk",
            ))

        if binaries["gradle"]:
            ok, version = version_of("gradle")
            results.append(CheckResult(
                name="Gradle", category="Android Toolchain", status="ok",
                details=(version.splitlines()[0] if version else binaries["gradle"]),
                code="gradle", cached=cached_flag("gradle"),
            ))
            gradle_version = _gradle_version(version or "")
            jdk_major = _jdk_major(version_of("java")[1]) if binaries["java"] else None
            # Verified facts: Java 17 support arrived in Gradle 7.3, and Gradle 9
            # requires Java 17 or newer to start.  Termux has never packaged
            # openjdk-11, so the previous "use JDK 11" advice was unusable.
            if gradle_version and jdk_major is not None:
                problem = None
                fix = None
                if gradle_version < (7, 3) and jdk_major >= 17:
                    problem = (f"Gradle {gradle_version[0]}.{gradle_version[1]} predates "
                               "JDK 17 support and cannot run on this JDK.")
                    fix = packages.install_hint(("gradle",), "Upgrade Gradle with: ")
                elif gradle_version >= (9, 0) and jdk_major < 17:
                    problem = (f"Gradle {gradle_version[0]}.{gradle_version[1]} requires "
                               "JDK 17 or newer to start.")
                    fix = packages.install_hint(("jdk",), "Install JDK 17 with: ")
                if problem:
                    results.append(CheckResult(
                        name="JDK / Gradle Compatibility", category="Android Toolchain",
                        status="warning",
                        details=f"JDK {jdk_major} with Gradle "
                                f"{gradle_version[0]}.{gradle_version[1]}",
                        problem=problem,
                        fix=fix,
                        code="jdk_gradle_compatibility",
                    ))
        else:
            results.append(CheckResult(
                name="Gradle", category="Android Toolchain", status="missing",
                details="Not installed globally (gradlew can be used inside projects)",
                problem="No global gradle. Projects with a Gradle wrapper can still build.",
                fix=packages.install_hint(("gradle",), "Install Gradle with: "),
                code="gradle",
            ))

        sdk_candidates = get_android_sdk_candidates()
        sdk_info = None
        if sdk_candidates:
            sdk_path = sdk_candidates[0]
            sdk_info = _sdk_details(sdk_path)
            has_platforms = bool(sdk_info["platforms"])
            has_build_tools = bool(sdk_info["build_tools"])
            status = "ok" if (has_platforms and has_build_tools) else "warning"
            details_bits = [f"Path: {sdk_path}"]
            details_bits.append(
                f"Platforms: {len(sdk_info['platforms'])}" if has_platforms else "Platforms: missing")
            details_bits.append(
                f"Build-tools: {len(sdk_info['build_tools'])}" if has_build_tools
                else "Build-tools: missing")
            if sdk_info["platforms"]:
                details_bits.append("API " + ", ".join(sdk_info["platforms"][-3:]))
            results.append(CheckResult(
                name="Android SDK", category="Android Toolchain", status=status,
                details=" | ".join(details_bits),
                problem="Android SDK is missing platforms or build-tools." if status != "ok" else None,
                fix=("Run 'wob deps install android-sdk' to add the missing SDK packages."
                     if status != "ok" else None),
                code="android_sdk",
            ))
        else:
            results.append(CheckResult(
                name="Android SDK", category="Android Toolchain", status="missing",
                details="Not found in standard paths or $ANDROID_HOME",
                problem="The Android SDK is required to compile native Android apps.",
                fix=("Termux has no Android SDK package. " + packages.android_sdk_hint()
                     + " Then set ANDROID_HOME in ~/.bashrc."),
                code="android_sdk",
            ))

        build_tools_found = []
        if aapt2_bin:
            build_tools_found.append("aapt2")
        if apksigner_bin:
            build_tools_found.append("apksigner")
        if zipalign_bin:
            build_tools_found.append("zipalign")
        missing_tools = [name for name, found in
                         (("aapt2", aapt2_bin), ("apksigner", apksigner_bin),
                          ("zipalign", zipalign_bin)) if not found]
        if not missing_tools:
            results.append(CheckResult(
                name="Android Build Tools", category="Android Toolchain", status="ok",
                details=", ".join(build_tools_found) + " on PATH",
                code="android_build_tools",
            ))
        else:
            # Termux: "aapt" installs aapt and zipalign, aapt2 is a split package
            # of the same build, and apksigner is separate (it pulls openjdk-21).
            # The old "aapt apksigner" hint therefore never satisfied aapt2.
            results.append(CheckResult(
                name="Android Build Tools", category="Android Toolchain",
                status="warning" if build_tools_found else "missing",
                details=(", ".join(build_tools_found) + " on PATH; missing "
                         + ", ".join(missing_tools)) if build_tools_found
                else ", ".join(missing_tools) + " not found",
                problem="These utilities inspect and package APKs directly; Wobble falls back "
                        "to its pure-Python parser without them.",
                fix=packages.install_hint(("aapt", "aapt2", "apksigner"),
                                          "Install Android build tools: "),
                code="android_build_tools",
            ))

        if binaries["adb"]:
            ok, version = version_of("adb")
            results.append(CheckResult(
                name="ADB (Android Debug Bridge)", category="Android Toolchain", status="ok",
                details=(version.splitlines()[0] if version else binaries["adb"]),
                code="adb", cached=cached_flag("adb"),
            ))
        else:
            results.append(CheckResult(
                name="ADB (Android Debug Bridge)", category="Android Toolchain", status="missing",
                details="Not installed (optional on-device)",
                problem="ADB is optional on the device itself; Wobble uses Android's installer.",
                fix=packages.install_hint(("adb",), "For ADB over Wi-Fi / localhost: "),
                code="adb",
            ))

    # -- Wobble's own installation ------------------------------------
    selfcheck_ms = 0.0
    if wanted("Wobble Runtime") and include_self:
        self_started = time.monotonic()
        results.extend(_wobble_runtime_checks())
        selfcheck_ms = round((time.monotonic() - self_started) * 1000, 1)

    # Keep the category order stable regardless of probe order. The sort is
    # stable, so insertion order inside a category is preserved.
    order = {name: index for index, name in enumerate(CATEGORIES)}
    results.sort(key=lambda item: order.get(item.category, 99))
    probe_ms_total = round(probe_ms + selfcheck_ms, 1)
    inspect_environment.last_timings = {
        "probes_ms": probe_ms,
        "selfcheck_ms": selfcheck_ms,
        "total_ms": round((time.monotonic() - started) * 1000, 1),
        "probe_sections_ms": probe_ms_total,
        "quick": quick,
        "refresh": refresh,
    }
    return results


inspect_environment.last_timings = {}  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Report

# ---------------------------------------------------------------------------
# Install advice
# ---------------------------------------------------------------------------
#: Doctor checks that map onto installable package keys. Optional tools (PHP,
#: ADB) are deliberately absent: they are never required to build anything and
#: including them turned the "Quick fix" line into noise.
QUICK_FIX_CHECKS = (
    ("Git", ("git",)),
    ("Node.js", ("nodejs",)),
    ("npm", ("nodejs",)),
    ("Java / JDK", ("jdk",)),
    ("JAVA_HOME", ("jdk",)),
    ("JDK / Gradle Compatibility", ("jdk", "gradle")),
    ("Gradle", ("gradle",)),
    ("Android Build Tools", ("aapt", "aapt2", "apksigner")),
)


def build_quick_fix(results: List["CheckResult"]) -> Dict[str, Any]:
    """Turn failing checks into one verified, platform-appropriate command.

    The command is resolved through :mod:`wobble.core.packages`, so a Debian
    host receives ``sudo apt install -y openjdk-17-jdk`` rather than Termux's
    ``pkg install -y openjdk-17``, and unavailable Android build-tools are
    reported instead of being silently omitted.
    """
    failing = {result.name for result in results if result.status in ("missing", "warning")}
    keys: List[str] = []
    for check_name, check_keys in QUICK_FIX_CHECKS:
        if check_name not in failing:
            continue
        for key in check_keys:
            if key not in keys:
                keys.append(key)

    family = packages.package_family()
    command = packages.install_command(keys, family)
    unsupported = packages.unsupported_keys(keys, family)
    notes: List[str] = []
    if command and family == packages.TERMUX:
        notes.append("Run 'pkg update' first if a package is reported as unavailable.")
        if "jdk" in keys:
            notes.append("Termux also ships openjdk-21 and openjdk-25; the Android "
                         "Gradle Plugin needs JDK 17 or newer.")
    if unsupported:
        notes.append("Google's Android build-tools are not packaged for "
                     f"{packages.family_label(family)}: install them with sdkmanager.")
    return {
        "command": command,
        "note": " ".join(notes) if notes else None,
        "packages": packages.packages_for(keys, family),
        "unavailable": unsupported,
        "package_manager": family or None,
    }


# ---------------------------------------------------------------------------
def _counts(results: List[CheckResult]) -> Dict[str, int]:
    counts = {"ok": 0, "warning": 0, "missing": 0, "error": 0}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    return counts


def doctor_exit_code(report: Dict[str, Any], fail_on: str = "never") -> int:
    """Translate a report into a shell exit status for CI use."""
    threshold = FAIL_ON_RANK.get(fail_on, 99)
    rank = {"ok": 0, "warning": 1, "missing": 2, "error": 3}
    worst = max((rank.get(check["status"], 0) for check in report.get("checks", [])), default=0)
    return 1 if worst >= threshold else 0


def run_doctor(json_mode: bool = False, quick: bool = False, only: Optional[str] = None,
               fail_on: str = "never", timings: bool = False, no_cache: bool = False,
               save_baseline: bool = False, save: bool = True) -> Dict[str, Any]:
    """Run doctor and render an ASCII report (or return the JSON dictionary)."""
    started = time.monotonic()
    if no_cache:
        os.environ["WOBBLE_NO_CACHE"] = "1"

    selected = resolve_categories(only)
    results = inspect_environment(quick=quick, only=only, refresh=no_cache)
    counts = _counts(results)
    status = "healthy" if counts["missing"] == 0 and counts["error"] == 0 else "needs_attention"

    # Regression detection: only meaningful for unfiltered runs, because a
    # filtered run would otherwise look like "all other checks disappeared".
    diff: Dict[str, Any] = {"regressions": [], "recovered": [], "new": [], "removed": [],
                            "persistent": [], "previous_at": None}
    will_save = bool(save or save_baseline)
    baseline_state = "saved" if will_save else "skipped"
    if selected:
        baseline_state = "skipped (filtered run)"
    else:
        report_for_diff = {"checks": [{"name": r.name, "status": r.status} for r in results]}
        try:
            diff = health.diff_and_update(report_for_diff, save=will_save)
        except Exception:
            baseline_state = "unavailable"

    # Regressions are themselves a health signal: surface them in the counts by
    # adding a synthetic error/warning row rather than hiding the change.
    if diff.get("regressions"):
        names = ", ".join(item["name"] for item in diff["regressions"][:4])
        results.append(CheckResult(
            name="Regressions Since Last Run",
            category="Wobble Runtime",
            status="warning",
            details=f"{len(diff['regressions'])} check(s) got worse: {names}",
            problem="A previously passing check is now failing; something changed on this device.",
            fix="Read the affected checks above, then fix them or re-run 'wob doctor --json'.",
            code="regressions",
        ))
        counts = _counts(results)
        status = "needs_attention"

    probe_cache = probecache.stats()
    if not no_cache:
        probecache.flush()

    total_ms = round((time.monotonic() - started) * 1000, 1)
    report_data: Dict[str, Any] = {
        "status": status,
        "counts": counts,
        "checks": [r.to_dict() for r in results],
        "categories": list(CATEGORIES),
        "only": selected,
        "lan_ip": get_lan_ip(),
        "elapsed_seconds": round((time.monotonic() - started), 3),
        "elapsed_ms": total_ms,
        "quick": quick,
        "cache": probe_cache,
        "timings": getattr(inspect_environment, "last_timings", {}),
        "regressions": diff.get("regressions", []),
        "recovered": diff.get("recovered", []),
        "new_checks": diff.get("new", []),
        "removed_checks": diff.get("removed", []),
        "persistent": diff.get("persistent", []),
        "previous_run": diff.get("previous_at"),
        "baseline": baseline_state,
        "fail_on": fail_on,
        "quick_fix": build_quick_fix(results),
    }
    report_data["exit_code"] = doctor_exit_code(report_data, fail_on)

    if json_mode:
        import json

        print(json.dumps(report_data, indent=2, default=str))
        return report_data

    logger = get_logger()
    color = logger.use_color
    print()
    print(theme.banner(color, theme.TAGLINE))
    print()
    print(theme.rule("environment doctor", width=70, use_color=color))

    if selected:
        print()
        print(theme.paint(f"  filtered to: {', '.join(selected)}", theme.DIM, enabled=color))

    current_category = ""
    for result in results:
        if result.category != current_category:
            current_category = result.category
            print()
            print(theme.paint(f"  {current_category.upper()}", theme.BOLD, theme.BRIGHT_WHITE,
                              enabled=color))
        print(f"  {theme.badge(result.status, color)} {result.name:<26} {result.details}")
        if result.problem:
            print(f"        {theme.paint('problem:', theme.DIM, enabled=color)} {result.problem}")
        if result.fix:
            print(f"        {theme.paint('fix:', theme.CYAN, enabled=color)} {result.fix}")

    # -- change history ----------------------------------------------
    if diff.get("regressions") or diff.get("recovered") or diff.get("persistent"):
        print()
        print(theme.rule("changes since last run", width=70, use_color=color))
        for item in diff.get("regressions", [])[:6]:
            print(f"  {theme.badge('warning', color)} regression  {item['name']}  "
                  f"{item['from']} -> {item['to']}")
        for item in diff.get("recovered", [])[:6]:
            print(f"  {theme.badge('ok', color)} recovered   {item['name']}  "
                  f"{item['from']} -> {item['to']}")
        for item in diff.get("persistent", [])[:6]:
            print(f"  {theme.badge('warning', color)} persistent  {item['name']}  "
                  f"failing for {item['days']}d (since {item['since_iso']})")
        if not diff.get("regressions") and not diff.get("recovered"):
            print(f"  {theme.paint('no status changes', theme.DIM, enabled=color)}")

    # -- summary ------------------------------------------------------
    total = len(results) or 1
    score = int(round(100 * (counts["ok"] + 0.55 * counts["warning"]) / total))
    if counts["error"]:
        score = min(score, 40)
    summary = [
        f"{theme.progress_bar(score, width=20, use_color=color, invert=True)}  health",
        f"{theme.badge('ok', color)} passed {counts['ok']}   "
        f"{theme.badge('warning', color)} warnings {counts['warning']}",
        f"{theme.badge('missing', color)} missing {counts['missing']}   "
        f"{theme.badge('error', color)} errors {counts['error']}",
        f"{theme.paint('scan', theme.DIM)} {report_data['elapsed_ms']} ms"
        + ("  (quick)" if quick else "")
        + (f"  cache {probe_cache['fresh']} probes"
           if probe_cache.get("enabled") and probe_cache.get("fresh") else ""),
    ]
    if diff.get("regressions"):
        summary.append(f"{theme.paint('changes', theme.DIM)} {len(diff['regressions'])} "
                       f"regression(s) since last run")
    print()
    print(theme.box("summary", summary, width=70, use_color=color))

    if timings:
        print()
        timing_rows = []
        for key, value in (report_data.get("timings") or {}).items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                timing_rows.append(f"{key:<18} {value} ms")
            elif isinstance(value, bool):
                timing_rows.append(f"{key:<18} {'yes' if value else 'no'}")
        timing_rows.append(f"{'cache entries':<18} {probe_cache.get('fresh', 0)} fresh / "
                           f"{probe_cache.get('entries', 0)} total")
        print(theme.box("timings", timing_rows, width=70, use_color=color))

    quick_fix = report_data.get("quick_fix") or {}
    if quick_fix.get("command"):
        print()
        print(theme.paint("  Quick fix:", theme.BOLD, theme.YELLOW, enabled=color),
              quick_fix["command"])
        if quick_fix.get("note"):
            print(theme.paint(f"             {quick_fix['note']}", theme.DIM, enabled=color))
        elif quick_fix.get("unavailable"):
            print(theme.paint("             Some tools above are not packaged here; "
                              "see their individual fixes.", theme.DIM, enabled=color))

    if counts["missing"] == 0 and counts["error"] == 0 and counts["warning"] == 0:
        print()
        print(theme.paint("  All checks passed. Happy building.", theme.GREEN, theme.BOLD,
                          enabled=color))
    print()
    return report_data
