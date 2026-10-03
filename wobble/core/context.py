"""
Wobble Environment Context & Dynamic System Detection
Detects Termux, Android, architecture, memory, storage, paths dynamically without hardcoding.
"""

import os
import sys
import platform
import shutil
import socket
from pathlib import Path
from typing import Dict, Any, Optional, List


def is_termux() -> bool:
    """Detect whether the current runtime environment is Termux."""
    if "TERMUX_VERSION" in os.environ or "PREFIX" in os.environ:
        return True
    prefix = os.environ.get("PREFIX", "")
    if "com.termux" in prefix:
        return True
    return Path("/data/data/com.termux/files/usr").exists()


def get_prefix() -> Path:
    """Return the detected Termux prefix or system prefix dynamically."""
    if "PREFIX" in os.environ:
        return Path(os.environ["PREFIX"])
    if Path("/data/data/com.termux/files/usr").exists():
        return Path("/data/data/com.termux/files/usr")
    return Path(sys.prefix)


def get_home() -> Path:
    """Return the user home directory dynamically."""
    if "HOME" in os.environ:
        return Path(os.environ["HOME"])
    return Path.home()


def get_wobble_home() -> Path:
    """Return Wobble root data/config directory (~/.wobble)."""
    return get_home() / ".wobble"


def get_wobble_config_path() -> Path:
    """Return user configuration path (~/.config/wobble/config.json)."""
    cfg_dir = get_home() / ".config" / "wobble"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    return cfg_dir / "config.json"


def get_architecture() -> str:
    """Detect machine architecture normalized to standard naming."""
    raw = platform.machine().lower()
    if raw in ("aarch64", "arm64", "armv8l", "armv8"):
        return "aarch64"
    if raw in ("arm", "armv7l", "armv7", "armv6l"):
        return "arm"
    if raw in ("x86_64", "amd64"):
        return "x86_64"
    if raw in ("i686", "i386", "x86"):
        return "x86"
    return raw


def get_android_property(prop_name: str) -> Optional[str]:
    """Read an Android system property via /system/bin/getprop or build.prop without shell parsing."""
    getprop_bin = shutil.which("getprop") or "/system/bin/getprop"
    if os.path.exists(getprop_bin):
        try:
            import subprocess
            res = subprocess.run([getprop_bin, prop_name], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2)
            if res.returncode == 0:
                val = res.stdout.strip()
                if val:
                    return val
        except Exception:
            pass

    # Fallback to reading /system/build.prop if accessible
    for bp in ["/system/build.prop", "/default.prop"]:
        if os.path.exists(bp):
            try:
                with open(bp, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if line.startswith(f"{prop_name}="):
                            return line.split("=", 1)[1].strip()
            except Exception:
                pass
    return None


def get_android_version() -> Dict[str, Optional[str]]:
    """Detect Android release version and API level."""
    release = get_android_property("ro.build.version.release")
    sdk = get_android_property("ro.build.version.sdk")
    device_model = get_android_property("ro.product.model")
    device_brand = get_android_property("ro.product.brand")

    return {
        "release": release,
        "api_level": sdk,
        "model": device_model,
        "brand": device_brand
    }


def get_termux_version() -> Optional[str]:
    """Detect Termux application version."""
    if "TERMUX_VERSION" in os.environ:
        return os.environ["TERMUX_VERSION"]
    # Check dpkg status for termux-tools or termux-am
    dpkg_status = get_prefix() / "var" / "lib" / "dpkg" / "status"
    if dpkg_status.exists():
        try:
            with open(dpkg_status, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                for block in content.split("\n\n"):
                    if "Package: termux-tools" in block:
                        for line in block.splitlines():
                            if line.startswith("Version:"):
                                return line.split(":", 1)[1].strip()
        except Exception:
            pass
    return None


def get_storage_info(path: Optional[Path] = None) -> Dict[str, Any]:
    """Get available and total disk storage in human readable & bytes format."""
    target = path or get_home()
    try:
        usage = shutil.disk_usage(str(target))
        return {
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
            "total_human": _format_bytes(usage.total),
            "used_human": _format_bytes(usage.used),
            "free_human": _format_bytes(usage.free),
            "percent_used": round((usage.used / usage.total) * 100, 1) if usage.total > 0 else 0
        }
    except Exception as e:
        return {
            "error": str(e),
            "free_human": "Unknown",
            "percent_used": 0
        }


def get_memory_info() -> Dict[str, Any]:
    """Read system RAM info from /proc/meminfo where accessible on Linux/Android."""
    meminfo_file = Path("/proc/meminfo")
    if not meminfo_file.exists():
        return {"error": "proc/meminfo not accessible"}

    try:
        mem: Dict[str, int] = {}
        with open(meminfo_file, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                parts = line.split(":")
                if len(parts) == 2:
                    k = parts[0].strip()
                    val_str = parts[1].strip().split()[0]
                    if val_str.isdigit():
                        mem[k] = int(val_str) * 1024  # kB to bytes

        total = mem.get("MemTotal", 0)
        available = mem.get("MemAvailable", mem.get("MemFree", 0))
        used = total - available if total >= available else 0

        return {
            "total_bytes": total,
            "available_bytes": available,
            "used_bytes": used,
            "total_human": _format_bytes(total),
            "available_human": _format_bytes(available),
            "used_human": _format_bytes(used),
            "percent_used": round((used / total) * 100, 1) if total > 0 else 0
        }
    except Exception as e:
        return {"error": str(e), "available_human": "Unknown", "percent_used": 0}


def get_lan_ip() -> str:
    """
    Detect the device's local LAN IP address dynamically.
    Uses a UDP socket trick without making any outbound network calls.
    Falls back to 127.0.0.1 if offline.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Does not actually initiate a connection; used to query routing table for outbound interface
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except Exception:
        try:
            # Fallback attempt with Google DNS
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        except Exception:
            ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def find_tool(name: str) -> Optional[str]:
    """
    Locate an executable binary by name, searching standard PATH and Termux prefixes.
    Returns absolute path if found, None otherwise.
    """
    found = shutil.which(name)
    if found:
        return found

    prefix_bin = get_prefix() / "bin" / name
    if prefix_bin.is_file() and os.access(prefix_bin, os.X_OK):
        return str(prefix_bin)

    home_local_bin = get_home() / ".local" / "bin" / name
    if home_local_bin.is_file() and os.access(home_local_bin, os.X_OK):
        return str(home_local_bin)

    home_bin = get_home() / "bin" / name
    if home_bin.is_file() and os.access(home_bin, os.X_OK):
        return str(home_bin)

    return None


def get_android_sdk_candidates() -> List[Path]:
    """Return potential Android SDK paths dynamically based on standard Termux & user setups."""
    candidates = []

    # 1. Environment variables
    for env_var in ["ANDROID_HOME", "ANDROID_SDK_ROOT"]:
        if env_var in os.environ:
            p = Path(os.environ[env_var])
            if p.exists() and p not in candidates:
                candidates.append(p)

    # 2. Common Termux locations
    termux_sdk = get_prefix() / "share" / "android-sdk"
    if termux_sdk.exists() and termux_sdk not in candidates:
        candidates.append(termux_sdk)

    opt_sdk = get_prefix() / "opt" / "android-sdk"
    if opt_sdk.exists() and opt_sdk not in candidates:
        candidates.append(opt_sdk)

    # 3. Home directory SDK setups
    home_sdk = get_home() / "android-sdk"
    if home_sdk.exists() and home_sdk not in candidates:
        candidates.append(home_sdk)

    wobble_sdk = get_wobble_home() / "android-sdk"
    if wobble_sdk.exists() and wobble_sdk not in candidates:
        candidates.append(wobble_sdk)

    return candidates


def get_java_home_candidates() -> List[Path]:
    """Return potential JAVA_HOME paths dynamically."""
    candidates = []

    if "JAVA_HOME" in os.environ:
        p = Path(os.environ["JAVA_HOME"])
        if p.exists():
            candidates.append(p)

    # Termux openjdk paths
    jvm_dir = get_prefix() / "lib" / "jvm"
    if jvm_dir.is_dir():
        for entry in jvm_dir.iterdir():
            if entry.is_dir() and (entry / "bin" / "java").exists():
                if entry not in candidates:
                    candidates.append(entry)

    return candidates


def _format_bytes(b: int) -> str:
    """Format bytes into human-readable string (KB, MB, GB)."""
    if b < 1024:
        return f"{b} B"
    for unit in ["KB", "MB", "GB", "TB"]:
        b /= 1024.0
        if b < 1024:
            return f"{b:.1f} {unit}"
    return f"{b:.1f} PB"


def get_full_environment_report() -> Dict[str, Any]:
    """Assemble a comprehensive dictionary of the environment state."""
    return {
        "termux": {
            "is_termux": is_termux(),
            "prefix": str(get_prefix()),
            "home": str(get_home()),
            "version": get_termux_version()
        },
        "platform": {
            "system": platform.system(),
            "architecture": get_architecture(),
            "raw_machine": platform.machine(),
            "python_version": platform.python_version()
        },
        "android": get_android_version(),
        "storage": get_storage_info(),
        "memory": get_memory_info(),
        "network": {
            "lan_ip": get_lan_ip()
        },
        "sdk_candidates": [str(p) for p in get_android_sdk_candidates()],
        "java_home_candidates": [str(p) for p in get_java_home_candidates()]
    }
