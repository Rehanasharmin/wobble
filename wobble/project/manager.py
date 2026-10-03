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
from wobble.project.spec import ProjectSpec, PROJECT_SPEC_FILENAME

PROJECT_REGISTRY_FILE = get_wobble_home() / "projects.json"


def _load_registry() -> Dict[str, str]:
    """Load project registry mapping {name: absolute_path}."""
    if PROJECT_REGISTRY_FILE.exists():
        try:
            with open(PROJECT_REGISTRY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_registry(reg: Dict[str, str]):
    """Save project registry."""
    try:
        PROJECT_REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(PROJECT_REGISTRY_FILE, "w", encoding="utf-8") as f:
            json.dump(reg, f, indent=2)
    except Exception:
        pass


def register_project(name: str, path: Path):
    reg = _load_registry()
    reg[name] = str(path.resolve())
    _save_registry(reg)


def unregister_project(name: str):
    reg = _load_registry()
    if name in reg:
        del reg[name]
        _save_registry(reg)


def find_current_project(start_dir: Optional[Path] = None) -> Optional[ProjectSpec]:
    """
    Search current directory and ancestor directories for a Wobble project or
    infer one from typical project markers (build.gradle, package.json).
    """
    curr = (start_dir or Path.cwd()).resolve()

    # Search upwards for wobble.json
    p = curr
    while True:
        spec = ProjectSpec.load_from_dir(p)
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
            # Stale registry entry
            unregister_project(name)

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
    try:
        for f in path.rglob("*"):
            # skip .git and node_modules for quick stats
            if ".git" in f.parts or "node_modules" in f.parts or ".gradle" in f.parts:
                continue
            if f.is_file():
                file_count += 1
                total_size += f.stat().st_size
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
