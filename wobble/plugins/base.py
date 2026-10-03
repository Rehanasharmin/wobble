"""
Wobble Plugin Interface Base Class
Defines the contract for framework plugins to implement project creation, detection,
development, build, test, run, and cleanup commands.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Dict, Any, Optional


class BasePlugin(ABC):
    """Abstract base class for all Wobble framework plugins."""

    name: str = "base"
    version: str = "1.0.0"
    description: str = "Base plugin"
    category: str = "general"  # "android", "web", or "general"
    required_system_packages: List[str] = []
    required_tools: List[str] = []

    def __init__(self):
        pass

    @abstractmethod
    def detect(self, project_path: Path) -> bool:
        """Return True if project_path matches this framework."""
        pass

    @abstractmethod
    def create_project(self, name: str, target_dir: Path, options: Optional[Dict[str, Any]] = None) -> bool:
        """Scaffold a new project in target_dir."""
        pass

    def get_dev_command(self, project_path: Path, options: Optional[Dict[str, Any]] = None) -> Optional[List[str]]:
        """Return CLI command array to start development server or watch mode."""
        return None

    def get_build_command(self, project_path: Path, options: Optional[Dict[str, Any]] = None) -> Optional[List[str]]:
        """Return CLI command array to build the project for distribution."""
        return None

    def get_test_command(self, project_path: Path, options: Optional[Dict[str, Any]] = None) -> Optional[List[str]]:
        """Return CLI command array to run tests."""
        return None

    def get_run_command(self, project_path: Path, options: Optional[Dict[str, Any]] = None) -> Optional[List[str]]:
        """Return CLI command array to run/serve the project."""
        return None

    def get_clean_command(self, project_path: Path, options: Optional[Dict[str, Any]] = None) -> Optional[List[str]]:
        """Return CLI command array to clean temporary build outputs."""
        return None

    def check_prerequisites(self) -> Dict[str, Any]:
        """Verify if the host environment has all required tools for this plugin."""
        from wobble.core.context import find_tool
        missing = []
        for tool in self.required_tools:
            if not find_tool(tool):
                missing.append(tool)

        return {
            "ready": len(missing) == 0,
            "missing_tools": missing,
            "required_packages": self.required_system_packages
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serialize plugin metadata for machine-readable JSON."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "category": self.category,
            "required_tools": self.required_tools,
            "required_system_packages": self.required_system_packages,
            "prerequisites": self.check_prerequisites()
        }
