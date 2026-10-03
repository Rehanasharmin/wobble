"""
Wobble Plugin Loader & Registry
Discovers, validates, and manages built-in and user-contributed plugins.
"""

import os
import sys
import importlib
import importlib.util
from pathlib import Path
from typing import Dict, List, Optional

from wobble.plugins.base import BasePlugin
from wobble.core.config import get_config
from wobble.core.logger import get_logger

_PLUGINS_REGISTRY: Dict[str, BasePlugin] = {}
_INITIALIZED: bool = False


def register_plugin(plugin: BasePlugin):
    """Register a plugin instance."""
    _PLUGINS_REGISTRY[plugin.name] = plugin


def get_plugin(name: str) -> Optional[BasePlugin]:
    """Retrieve a plugin by name."""
    init_plugins()
    return _PLUGINS_REGISTRY.get(name)


def list_plugins() -> List[BasePlugin]:
    """Return all registered plugins."""
    init_plugins()
    return list(_PLUGINS_REGISTRY.values())


def detect_plugin_for_path(path: Path) -> Optional[BasePlugin]:
    """
    Detect the best matching framework plugin for a given directory.
    Checks plugins in priority order.
    """
    init_plugins()
    for plugin in _PLUGINS_REGISTRY.values():
        try:
            if plugin.detect(path):
                return plugin
        except Exception:
            continue
    return None


def init_plugins():
    """Discover and register all built-in and user plugins once."""
    global _INITIALIZED
    if _INITIALIZED:
        return

    # 1. Discover built-in plugins
    builtin_dir = Path(__file__).parent / "builtin"
    if builtin_dir.is_dir():
        for entry in builtin_dir.iterdir():
            if entry.is_dir() and not entry.name.startswith("_"):
                plugin_file = entry / "plugin.py"
                if plugin_file.exists():
                    _load_plugin_module(f"wobble.plugins.builtin.{entry.name}.plugin", plugin_file)

    # 2. Discover user plugins in ~/.wobble/plugins
    cfg = get_config()
    custom_dir_str = cfg.get("custom_plugins_dir")
    if custom_dir_str:
        custom_dir = Path(custom_dir_str)
        if custom_dir.is_dir():
            for entry in custom_dir.iterdir():
                if entry.is_dir() and not entry.name.startswith("_"):
                    plugin_file = entry / "plugin.py"
                    if plugin_file.exists():
                        _load_plugin_module(f"wobble_user_plugin_{entry.name}", plugin_file)

    _INITIALIZED = True


def _load_plugin_module(module_name: str, file_path: Path):
    """Dynamically load a plugin module and register any BasePlugin subclass."""
    try:
        spec = importlib.util.spec_from_file_location(module_name, str(file_path))
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # Search module for BasePlugin subclasses
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and issubclass(attr, BasePlugin) and attr is not BasePlugin:
                    instance = attr()
                    register_plugin(instance)
    except Exception as e:
        # Avoid crashing core if a single plugin fails to load
        get_logger().warn(f"Failed to load plugin at {file_path}: {e}")
