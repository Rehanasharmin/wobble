"""
Wobble Project Manager
Orchestrates project creation, discovery, indexing, inspection, and navigation.
"""

import os
import json
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional

from wobble.core.context import get_wobble_home, get_home
from wobble.core.logger import get_logger
from wobble.core.executor import run_command
from wobble.core.errors import RegistryError
from wobble.core.fsutil import atomic_write_json, backup_corrupted_file
from wobble.project.spec import ProjectSpec, PROJECT_SPEC_FILENAME

PROJECT_REGISTRY_FILE = get_wobble_home() / "projects.json"


def _load_registry() -> Dict[str, str]:
    """Load {name: absolute_path}, preserving corrupt data before recovery."""
    try:
        with PROJECT_REGISTRY_FILE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError("project registry root must be a JSON object")
    except FileNotFoundError:
        return {}
    except OSError as exc:
        raise RegistryError(
            f"Cannot read project registry '{PROJECT_REGISTRY_FILE}': {exc}",
            code="registry_read_failed",
            hint="Check the file and ~/.wobble directory permissions.",
        ) from exc
    except (json.JSONDecodeError, UnicodeError, ValueError) as exc:
        try:
            backup = backup_corrupted_file(PROJECT_REGISTRY_FILE)
            atomic_write_json(PROJECT_REGISTRY_FILE, {})
        except OSError as recovery_error:
            raise RegistryError(
                f"Project registry is invalid and could not be recovered safely: {recovery_error}",
                code="registry_recovery_failed",
                hint=f"Repair or remove {PROJECT_REGISTRY_FILE} manually; its data was not overwritten.",
            ) from recovery_error
        get_logger().warn(f"Invalid project registry was preserved at '{backup}'; starting with an empty registry ({exc}).")
        return {}

    # Individual malformed entries are ignored without discarding valid ones.
    return {str(key): value for key, value in data.items() if isinstance(value, str)}


def _save_registry(reg: Dict[str, str]) -> None:
    """Save atomically and report failure instead of claiming a write succeeded."""
    try:
        atomic_write_json(PROJECT_REGISTRY_FILE, reg)
    except Exception as exc:
        raise RegistryError(
            f"Cannot save project registry '{PROJECT_REGISTRY_FILE}': {exc}",
            code="registry_write_failed",
            hint="Check available disk space and ~/.wobble permissions, then retry.",
        ) from exc


def register_project(name: str, path: Path) -> None:
    reg = _load_registry()
    reg[name] = str(path.resolve())
    _save_registry(reg)


def unregister_project(name: str) -> bool:
    """Remove a registry entry and return whether it existed."""
    reg = _load_registry()
    if name not in reg:
        return False
    del reg[name]
    _save_registry(reg)
    return True


def find_current_project(start_dir: Optional[Path] = None) -> Optional[ProjectSpec]:
    """
    Search current directory and ancestor directories for a Wobble project or
    infer one from typical project markers (build.gradle, package.json).
    """
    curr = (start_dir or Path.cwd()).resolve()

    # Search upwards for wobble.json
    p = curr
    while True:
        spec = ProjectSpec.load_from_dir(p, strict=True)
        if spec:
            return spec
        if p.parent == p:
            break
        p = p.parent

    # If no wobble.json, try inferring from directory markers
    if (curr / "app" / "build.gradle").exists() or (curr / "build.gradle").exists():
        return ProjectSpec(
            name=curr.name,
            project_type="android",
            framework="android",
            path=curr,
            description="Inferred Android Gradle project"
        )

    if (curr / "package.json").exists() or (curr / "index.html").exists():
        return ProjectSpec(
            name=curr.name,
            project_type="web",
            framework="web",
            path=curr,
            description="Inferred Web project"
        )

    return None


def list_projects(scan_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """List registered projects plus any projects found in scan_dir or current directory."""
    results: Dict[str, Dict[str, Any]] = {}

    # 1. Registered projects
    reg = _load_registry()
    stale: List[str] = []
    for name, p_str in list(reg.items()):
        p = Path(p_str)
        if p.exists():
            spec = ProjectSpec.load_from_dir(p)
            if spec:
                results[name] = {
                    "name": name,
                    "path": str(p),
                    "type": spec.project_type,
                    "framework": spec.framework,
                    "version": spec.version,
                    "registered": True
                }
            else:
                results[name] = {
                    "name": name,
                    "path": str(p),
                    "type": "unknown",
                    "framework": "unknown",
                    "version": "0.1.0",
                    "registered": True
                }
        else:
            # Stale registry entry; prune in one batched save below
            stale.append(name)

    if stale:
        for name in stale:
            reg.pop(name, None)
        _save_registry(reg)

    # 2. Scan directory (defaults to current working directory)
    scan_root = scan_dir or Path.cwd()
    if scan_root.is_dir():
        # Check scan_root itself
        root_spec = ProjectSpec.load_from_dir(scan_root)
        if root_spec and root_spec.name not in results:
            results[root_spec.name] = {
                "name": root_spec.name,
                "path": str(scan_root),
                "type": root_spec.project_type,
                "framework": root_spec.framework,
                "version": root_spec.version,
                "registered": False
            }

        # Check immediate subdirectories
        try:
            for item in scan_root.iterdir():
                if item.is_dir() and not item.name.startswith("."):
                    sub_spec = ProjectSpec.load_from_dir(item)
                    if sub_spec and sub_spec.name not in results:
                        results[sub_spec.name] = {
                            "name": sub_spec.name,
                            "path": str(item),
                            "type": sub_spec.project_type,
                            "framework": sub_spec.framework,
                            "version": sub_spec.version,
                            "registered": False
                        }
        except Exception:
            pass

    return list(results.values())


def get_project_info(project_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Retrieve detailed metadata and metrics for the project."""
    spec = find_current_project(project_dir)
    if not spec:
        return None

    path = spec.path
    file_count = 0
    total_size = 0
    skip_dirs = {".git", "node_modules", ".gradle", ".cache", ".wobble", "__pycache__", ".next", "dist", "build", ".venv"}
    try:
        for dirpath, dirnames, filenames in os.walk(path):
            dirnames[:] = [d for d in dirnames if d not in skip_dirs]
            for f in filenames:
                fp = Path(dirpath) / f
                try:
                    total_size += fp.stat().st_size
                    file_count += 1
                except Exception:
                    pass
    except Exception:
        pass

    info = spec.to_dict()
    info["metrics"] = {
        "file_count": file_count,
        "total_size_bytes": total_size,
        "total_size_human": _format_bytes(total_size)
    }
    return info


def _format_bytes(b: int) -> str:
    if b < 1024:
        return f"{b} B"
    for unit in ["KB", "MB", "GB"]:
        b /= 1024.0
        if b < 1024:
            return f"{b:.1f} {unit}"
    return f"{b:.1f} TB"
