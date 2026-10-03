"""
Wobble Project Specification & wobble.json Manager
Provides schema validation, serialization, and deserialization of project metadata.
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from wobble import __version__

PROJECT_SPEC_FILENAME = "wobble.json"


class ProjectSpec:
    def __init__(
        self,
        name: str,
        project_type: str,
        framework: str,
        path: Path,
        version: str = "0.1.0",
        description: str = "",
        package_id: Optional[str] = None,
        scripts: Optional[Dict[str, str]] = None,
        dependencies: Optional[Dict[str, Any]] = None,
        extra: Optional[Dict[str, Any]] = None
    ):
        self.name = name
        self.project_type = project_type  # "android" or "web"
        self.framework = framework
        self.path = Path(path).resolve()
        self.version = version
        self.description = description
        self.package_id = package_id
        self.scripts = scripts or {}
        self.dependencies = dependencies or {"system": [], "project": {}}
        self.extra = extra or {}
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.wobble_version = __version__

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "name": self.name,
            "version": self.version,
            "type": self.project_type,
            "framework": self.framework,
            "description": self.description,
            "wobble_version": self.wobble_version,
            "created_at": self.created_at,
            "scripts": self.scripts,
            "dependencies": self.dependencies
        }
        if self.package_id:
            data["package_id"] = self.package_id
        if self.extra:
            data.update(self.extra)
        return data

    def save(self, filepath: Optional[Path] = None):
        target = filepath or (self.path / PROJECT_SPEC_FILENAME)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load_from_dir(cls, directory: Path) -> Optional["ProjectSpec"]:
        spec_path = Path(directory) / PROJECT_SPEC_FILENAME
        if not spec_path.exists():
            return None
        try:
            with open(spec_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            spec = cls(
                name=data.get("name", directory.name),
                project_type=data.get("type", "web"),
                framework=data.get("framework", "unknown"),
                path=directory,
                version=data.get("version", "0.1.0"),
                description=data.get("description", ""),
                package_id=data.get("package_id"),
                scripts=data.get("scripts", {}),
                dependencies=data.get("dependencies", {"system": [], "project": {}})
            )
            spec.created_at = data.get("created_at", spec.created_at)
            spec.wobble_version = data.get("wobble_version", spec.wobble_version)
            return spec
        except Exception:
            return None
