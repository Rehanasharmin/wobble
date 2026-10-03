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

    # If none found in priority dirs, do a fast walk pruning heavy folders
    if not candidates and root.is_dir():
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in {".git", "node_modules", ".gradle", ".cache", ".wobble", "__pycache__"}]
            for f in filenames:
                if f.endswith(".apk"):
                    candidates.append(Path(dirpath) / f)

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
                "error": "ADB executable not found. Install android-tools (pkg install -y android-tools) or use standard method."
            }
        res = run_command([adb_bin, "install", "-r", str(path)], timeout=60)
        is_success = "Success" in res.stdout
        return {
            "success": is_success,
            "method": "adb",
            "output": (res.stdout or res.stderr).strip(),
            "message": "APK installed successfully via ADB." if is_success else f"ADB installation failed: {res.stderr or res.stdout}"
        }

    # 2. Termux-open method (Standard on-device Android workflow)
    if method in ("auto", "termux-open"):
        termux_open = find_tool("termux-open")
        if termux_open:
            # Pass content-type so Android knows immediately this is an APK to install
            res = run_command([termux_open, "--content-type", "application/vnd.android.package-archive", str(path)])
            if not res.success:
                res = run_command([termux_open, str(path)])
            if res.success:
                return {
                    "success": True,
                    "method": "termux-open",
                    "message": "Dispatched to Android Package Installer. Look at your phone screen to confirm installation."
                }
            elif method == "termux-open":
                return {
                    "success": False,
                    "method": "termux-open",
                    "error": f"termux-open failed: {res.stderr or res.stdout}"
                }

    # 3. Android Intent 'am start' fallback
    if method in ("auto", "am"):
        am_bin = find_tool("termux-am") or find_tool("am") or "/system/bin/am"
        if am_bin and os.path.exists(am_bin):
            res = run_command([
                am_bin, "start",
                "--user", "0",
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
            elif method == "am":
                return {
                    "success": False,
                    "method": "am",
                    "error": f"am start failed: {res.stderr or res.stdout}"
                }

    if method != "auto":
        return {
            "success": False,
            "method": method,
            "error": f"Requested install method '{method}' is not available on this system."
        }

    return {
        "success": False,
        "method": "none",
        "error": "Could not find 'termux-open' or 'am'. Make sure 'termux-tools' package is installed."
    }


def share_apk(apk_path: Path, dest_dir: Optional[Path] = None) -> Dict[str, Any]:
    """
    Export APK to Android shared storage (e.g. ~/storage/shared/Download).
    Makes the APK accessible directly in the Android Files / Downloads app.
    """
    path = Path(apk_path).resolve()
    if not path.is_file():
        return {"success": False, "error": f"APK file not found: {path}"}

    from wobble.core.context import get_home
    home = get_home()

    target_dest = None
    if dest_dir:
        target_dest = Path(dest_dir).resolve()
    else:
        # Check standard Termux shared storage paths
        download_candidates = [
            home / "storage" / "shared" / "Download",
            home / "storage" / "downloads",
            home / "storage" / "shared" / "Downloads",
            home / "storage" / "download"
        ]
        for cand in download_candidates:
            if cand.is_dir():
                target_dest = cand
                break

        if not target_dest:
            shared_cand = home / "storage" / "shared"
            if shared_cand.is_dir():
                target_dest = shared_cand

    if not target_dest or not target_dest.is_dir():
        return {
            "success": False,
            "error": (
                "Android shared storage directory not found (~/storage/shared/Download). "
                "Please run 'termux-setup-storage' in Termux and grant permission."
            )
        }

    try:
        import shutil
        dest_file = target_dest / path.name
        shutil.copy2(path, dest_file)
        return {
            "success": True,
            "source": str(path),
            "destination": str(dest_file),
            "message": f"Exported {path.name} to {dest_file}"
        }
    except Exception as e:
        return {"success": False, "error": f"Failed to export APK: {e}"}


def sign_apk(
    apk_path: Path,
    keystore: Optional[Path] = None,
    key_alias: Optional[str] = None,
    key_pass: Optional[str] = None
) -> Dict[str, Any]:
    """
    Sign an APK file using apksigner and debug or user keystore.
    """
    path = Path(apk_path).resolve()
    if not path.is_file():
        return {"success": False, "error": f"APK file not found: {path}"}

    apksigner_bin = find_tool("apksigner")
    if not apksigner_bin:
        return {
            "success": False,
            "error": "apksigner not found. Install it with: pkg install -y apksigner"
        }

    from wobble.core.context import get_wobble_home
    keystore_path = keystore
    if not keystore_path:
        default_ks = get_wobble_home() / "debug.keystore"
        if not default_ks.exists():
            keytool_bin = find_tool("keytool")
            if keytool_bin:
                default_ks.parent.mkdir(parents=True, exist_ok=True)
                gen_cmd = [
                    keytool_bin, "-genkeypair", "-v",
                    "-keystore", str(default_ks),
                    "-storepass", "android",
                    "-alias", "androiddebugkey",
                    "-keypass", "android",
                    "-keyalg", "RSA",
                    "-keysize", "2048",
                    "-validity", "10000",
                    "-dname", "CN=Android Debug,O=Android,C=US"
                ]
                res_gen = run_command(gen_cmd)
                if not res_gen.success:
                    return {
                        "success": False,
                        "error": f"Failed to generate debug keystore with keytool: {res_gen.stderr}"
                    }
            else:
                return {
                    "success": False,
                    "error": "No keystore provided and 'keytool' not found to generate debug keystore."
                }
        keystore_path = default_ks
        key_alias = key_alias or "androiddebugkey"
        key_pass = key_pass or "android"

    sign_cmd = [
        apksigner_bin, "sign",
        "--ks", str(keystore_path),
        "--ks-pass", f"pass:{key_pass}",
        "--ks-key-alias", key_alias or "androiddebugkey",
        str(path)
    ]

    res = run_command(sign_cmd, timeout=30)
    if res.success:
        return {
            "success": True,
            "apk": str(path),
            "keystore": str(keystore_path),
            "message": f"Successfully signed {path.name}"
        }
    else:
        return {
            "success": False,
            "apk": str(path),
            "error": f"apksigner failed: {res.stderr or res.stdout}"
        }


def _format_bytes(b: int) -> str:
    if b < 1024:
        return f"{b} B"
    for unit in ["KB", "MB", "GB"]:
        b /= 1024.0
        if b < 1024:
            return f"{b:.1f} {unit}"
    return f"{b:.1f} TB"
