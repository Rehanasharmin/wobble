"""
Wobble APK Inspector, Locator, and Installer
Inspects APK contents using zero-dependency zipfile/binary XML parsing or aapt,
locates build outputs, and triggers honest on-device installation.
"""

import os
import sys
import zipfile
import hashlib
import struct
from pathlib import Path
from typing import List, Dict, Any, Optional

from wobble.core.context import find_tool
from wobble.core.executor import run_command


def find_apks(project_root: Optional[Path] = None) -> List[Path]:
    """Search for generated .apk files in standard Gradle output directories or recursively."""
    root = (project_root or Path.cwd()).resolve()
    candidates: List[Path] = []

    priority_dirs = [
        root / "app" / "build" / "outputs" / "apk" / "debug",
        root / "app" / "build" / "outputs" / "apk" / "release",
        root / "build" / "outputs" / "apk" / "debug",
        root / "build" / "outputs" / "apk" / "release",
        root / "build" / "outputs" / "apk",
        root
    ]

    for p_dir in priority_dirs:
        if p_dir.is_dir():
            for item in p_dir.glob("*.apk"):
                if item not in candidates:
                    candidates.append(item)

    # If none found in priority dirs, do a recursive scan excluding node_modules / .git
    if not candidates and root.is_dir():
        for item in root.rglob("*.apk"):
            if "node_modules" not in item.parts and ".gradle" not in item.parts:
                candidates.append(item)

    # Sort candidates by modification time (newest first)
    candidates.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return candidates


def inspect_apk(apk_path: Path) -> Dict[str, Any]:
    """Exhaustively inspect an APK file's metadata, contents, architecture, and signature."""
    path = Path(apk_path).resolve()
    if not path.is_file():
        return {"error": f"File not found: {path}"}

    stat = path.stat()
    size_bytes = stat.st_size

    # Calculate SHA-256
    sha256_hash = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256_hash.update(chunk)
    sha256 = sha256_hash.hexdigest()

    # Inspect ZIP structure
    dex_files = []
    abis = set()
    has_manifest = False
    has_resources = False
    signatures = []

    try:
        with zipfile.ZipFile(path, "r") as zf:
            for info in zf.infolist():
                filename = info.filename
                if filename.endswith(".dex"):
                    dex_files.append(filename)
                elif filename == "AndroidManifest.xml":
                    has_manifest = True
                elif filename == "resources.arsc":
                    has_resources = True
                elif filename.startswith("lib/"):
                    parts = filename.split("/")
                    if len(parts) >= 2:
                        abis.add(parts[1])
                elif filename.startswith("META-INF/"):
                    if filename.endswith((".RSA", ".DSA", ".EC")):
                        signatures.append(filename)
    except Exception as e:
        return {"error": f"Invalid APK ZIP archive: {e}"}

    # Try extracting detailed Android package metadata
    metadata = _extract_badging_metadata(path)

    return {
        "file_name": path.name,
        "path": str(path),
        "size_bytes": size_bytes,
        "size_human": _format_bytes(size_bytes),
        "sha256": sha256,
        "package_name": metadata.get("package_name") or "Unknown",
        "version_code": metadata.get("version_code") or "Unknown",
        "version_name": metadata.get("version_name") or "Unknown",
        "min_sdk": metadata.get("min_sdk") or "Unknown",
        "target_sdk": metadata.get("target_sdk") or "Unknown",
        "app_label": metadata.get("app_label") or path.stem,
        "dex_files": dex_files,
        "native_abis": sorted(list(abis)) if abis else ["universal / no native libs"],
        "has_resources": has_resources,
        "signatures": signatures if signatures else ["v2/v3 or unsigned"],
        "permissions": metadata.get("permissions", [])
    }


def _extract_badging_metadata(apk_path: Path) -> Dict[str, Any]:
    """Attempt extraction via aapt or pure Python binary XML parser."""
    data: Dict[str, Any] = {}

    # 1. Try aapt / aapt2
    aapt_bin = find_tool("aapt") or find_tool("aapt2")
    if aapt_bin:
        try:
            res = run_command([aapt_bin, "dump", "badging", str(apk_path)], timeout=10)
            if res.success:
                permissions = []
                for line in res.stdout.splitlines():
                    if line.startswith("package:"):
                        for part in line.split():
                            if part.startswith("name='"):
                                data["package_name"] = part.split("'")[1]
                            elif part.startswith("versionCode='"):
                                data["version_code"] = part.split("'")[1]
                            elif part.startswith("versionName='"):
                                data["version_name"] = part.split("'")[1]
                    elif line.startswith("sdkVersion:'"):
                        data["min_sdk"] = line.split("'")[1]
                    elif line.startswith("targetSdkVersion:'"):
                        data["target_sdk"] = line.split("'")[1]
                    elif line.startswith("application-label:'"):
                        data["app_label"] = line.split("'")[1]
                    elif "uses-permission: name='" in line:
                        perm = line.split("name='")[1].split("'")[0]
                        permissions.append(perm)
                data["permissions"] = permissions
                return data
        except Exception:
            pass

    # 2. Pure Python fallback: extract strings from binary AndroidManifest.xml
    try:
        with zipfile.ZipFile(apk_path, "r") as zf:
            if "AndroidManifest.xml" in zf.namelist():
                raw_xml = zf.read("AndroidManifest.xml")
                extracted = _parse_axml_strings(raw_xml)
                data.update(extracted)
    except Exception:
        pass

    return data


def _parse_axml_strings(data: bytes) -> Dict[str, Any]:
    """Basic AXML string table extraction to locate package name without external dependencies."""
    result: Dict[str, Any] = {}
    try:
        # Check AXML magic header (0x00080003 in LE)
        if len(data) < 8 or data[0:2] != b'\x03\x00':
            return result

        # Extract ASCII / UTF-8 readable substrings from the string pool
        strings = []
        chars = []
        for b in data:
            if 32 <= b <= 126:
                chars.append(chr(b))
            else:
                if len(chars) >= 3:
                    s = "".join(chars)
                    if not s.isdigit() and s not in strings:
                        strings.append(s)
                chars = []

        perms = []
        for s in strings:
            if "android.permission." in s:
                perms.append(s)
            elif "." in s and not s.endswith(".xml") and not s.endswith(".png") and not s.startswith("android.") and not s.startswith("http"):
                if "package_name" not in result and len(s.split(".")) >= 2:
                    result["package_name"] = s

        result["permissions"] = perms
    except Exception:
        pass
    return result


def install_apk(apk_path: Path, method: str = "auto") -> Dict[str, Any]:
    """
    Safely trigger APK installation on Android without requiring root or ADB.
    Honest reporting: Returns whether intent was dispatched or rejected.
    """
    path = Path(apk_path).resolve()
    if not path.is_file():
        return {
            "success": False,
            "method": method,
            "error": f"APK file not found: {path}"
        }

    # 1. ADB method
    if method == "adb":
        adb_bin = find_tool("adb")
        if not adb_bin:
            return {
                "success": False,
                "method": "adb",
                "error": "ADB executable not found. Install android-tools or use standard method."
            }
        res = run_command([adb_bin, "install", "-r", str(path)], timeout=30)
        is_success = "Success" in res.stdout
        return {
            "success": is_success,
            "method": "adb",
            "output": (res.stdout or res.stderr).strip(),
            "message": "APK installed successfully via ADB." if is_success else f"ADB installation failed: {res.stderr or res.stdout}"
        }

    # 2. Termux-open method (Standard on-device Android workflow)
    termux_open = find_tool("termux-open")
    if termux_open:
        res = run_command([termux_open, str(path)])
        if res.success:
            return {
                "success": True,
                "method": "termux-open",
                "message": "Dispatched to Android Package Installer. Look at your phone screen to confirm installation."
            }

    # 3. Android Intent 'am start' fallback
    am_bin = find_tool("termux-am") or find_tool("am") or "/system/bin/am"
    if am_bin:
        res = run_command([
            am_bin, "start",
            "-a", "android.intent.action.VIEW",
            "-d", f"file://{path}",
            "-t", "application/vnd.android.package-archive"
        ])
        if res.success:
            return {
                "success": True,
                "method": "am_start",
                "message": "Dispatched VIEW intent to Android Package Installer. Check your screen to confirm installation."
            }

    return {
        "success": False,
        "method": "none",
        "error": "Could not find 'termux-open' or 'am'. Make sure 'termux-tools' package is installed."
    }


def _format_bytes(b: int) -> str:
    if b < 1024:
        return f"{b} B"
    for unit in ["KB", "MB", "GB"]:
        b /= 1024.0
        if b < 1024:
            return f"{b:.1f} {unit}"
    return f"{b:.1f} TB"
