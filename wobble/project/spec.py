"""
Wobble Project Specification & wobble.json Manager
Provides schema validation, serialization, and deserialization of project metadata.
"""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone
from wobble import __version__
from wobble.core.errors import ProjectSpecError
from wobble.core.fsutil import atomic_write_json

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
        try:
            atomic_write_json(target, self.to_dict())
        except Exception as exc:
            raise ProjectSpecError(
                f"Cannot save project specification '{target}': {exc}",
                code="project_spec_write_failed",
                hint="Check the project directory permissions and available disk space.",
                details={"path": str(target)},
            ) from exc

    @classmethod
    def load_from_dir(cls, directory: Path, *, strict: bool = False) -> Optional["ProjectSpec"]:
        """Load a project spec, optionally reporting malformed files.

        Directory scans stay tolerant by default. Commands operating on the
        current project use ``strict=True`` so a broken wobble.json is not
        misreported as "no project found".
        """
        directory = Path(directory)
        spec_path = directory / PROJECT_SPEC_FILENAME
        if not spec_path.exists():
            return None
        try:
            with spec_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, dict):
                raise ValueError("project specification root must be a JSON object")
            for key in ("name", "type", "framework"):
                if key in data and not isinstance(data[key], str):
                    raise ValueError(f"'{key}' must be a string")
            for key in ("scripts", "dependencies"):
                if key in data and not isinstance(data[key], dict):
                    raise ValueError(f"'{key}' must be a JSON object")
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
        except (OSError, UnicodeError, ValueError, TypeError, AttributeError) as exc:
            if strict:
                raise ProjectSpecError(
                    f"Cannot load project specification '{spec_path}': {exc}",
                    hint="Fix the JSON in wobble.json, or restore it from a known-good copy.",
                    details={"path": str(spec_path)},
                ) from exc
            return None
