"""
Wobble Plugin Loader & Registry
Discovers, validates, and manages built-in and user-contributed plugins.

Built-in plugins are imported by module name (fast, bytecode-cached) instead of
being re-parsed from disk on every run. User plugins are treated as untrusted
code: they are only loaded from ordinary, private directories, they must have a
safe name, and they can never shadow a built-in plugin.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import re
import stat
import sys
from pathlib import Path

from wobble.plugins.base import BasePlugin
from wobble.core.context import get_wobble_config_path, get_wobble_home
from wobble.core.logger import get_logger

_PLUGINS_REGISTRY: Dict[str, BasePlugin] = {}
_INITIALIZED: bool = False

# Explicit order keeps framework detection deterministic: more specific
# frameworks come before generic ones (react before vite, static last).
BUILTIN_PLUGIN_NAMES = (
    "android",
    "nextjs",
    "react",
    "vue",
    "svelte",
    "vite",
    "python_web",
    "php",
    "static_web",
)

_PLUGIN_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")


FRAMEWORK_ALIASES: Dict[str, str] = {
    "python": "python_web",
    "flask": "python_web",
    "fastapi": "python_web",
    "py": "python_web",
    "static": "static_web",
    "html": "static_web",
    "html5": "static_web",
    "next": "nextjs",
    "reactjs": "react",
    "vuejs": "vue",
    "sveltejs": "svelte",
}


def register_plugin(plugin: BasePlugin):
    """Register a plugin instance."""
    _PLUGINS_REGISTRY[plugin.name] = plugin


def get_plugin(name: str) -> Optional[BasePlugin]:
    """Retrieve a plugin by name or alias."""
    init_plugins()
    normalized = FRAMEWORK_ALIASES.get(name.lower(), name)
    return _PLUGINS_REGISTRY.get(normalized)


def list_plugins() -> List[BasePlugin]:
    """Return all registered plugins."""
    init_plugins()
    return list(_PLUGINS_REGISTRY.values())


def detect_plugin_for_path(path: Path) -> Optional[BasePlugin]:
    """Detect the best matching framework plugin for a given directory."""
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

    for name in BUILTIN_PLUGIN_NAMES:
        module_path = f"wobble.plugins.builtin.{name}.plugin"
        try:
            module = importlib.import_module(module_path)
        except Exception as exc:
            # A broken built-in should degrade gracefully, never kill the CLI.
            get_logger().warn(f"Failed to load built-in plugin '{name}': {exc}")
            continue
        _register_module(module, allow_override=False)

    _init_user_plugins()
    _INITIALIZED = True


def _register_module(module, allow_override: bool) -> Optional[BasePlugin]:
    """Instantiate and register every BasePlugin subclass found in a module."""
    registered = None
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if not (isinstance(attr, type) and issubclass(attr, BasePlugin) and attr is not BasePlugin):
            continue
        try:
            instance = attr()
        except Exception as exc:
            get_logger().warn(f"Skipping unloadable plugin class {attr_name}: {exc}")
            continue
        plugin_name = str(getattr(instance, "name", ""))
        if not _PLUGIN_NAME_RE.match(plugin_name):
            get_logger().warn(
                f"Ignoring plugin with unsafe name {plugin_name!r} (allowed: a-z, 0-9, _)."
            )
            continue
        if plugin_name in _PLUGINS_REGISTRY and not allow_override:
            continue
        register_plugin(instance)
        registered = instance
    return registered


# ---------------------------------------------------------------------------
# User plugins (untrusted)
# ---------------------------------------------------------------------------
def _custom_plugins_dir() -> Path:
    """
    Read the custom plugin directory without instantiating ConfigManager.

    This avoids creating ~/.config/wobble (and writing a default config file)
    just because a command happened to list plugins.
    """
    cfg_path = get_wobble_config_path()
    if cfg_path.is_file():
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            value = data.get("custom_plugins_dir") if isinstance(data, dict) else None
            if value:
                return Path(str(value)).expanduser()
        except (OSError, ValueError):
            pass
    return get_wobble_home() / "plugins"


def _allow_unsafe_plugins() -> bool:
    return os.environ.get("WOBBLE_ALLOW_UNSAFE_PLUGINS", "").strip().lower() in ("1", "true", "yes")


def _is_private(path: Path, kind: str = "file") -> bool:
    """Reject plugin files/dirs that other users or apps could modify."""
    try:
        info = path.stat()
    except OSError:
        return False
    expected = stat.S_ISREG if kind == "file" else stat.S_ISDIR
    if not expected(info.st_mode):
        return False
    return not (info.st_mode & (stat.S_IWGRP | stat.S_IWOTH))


def _init_user_plugins() -> None:
    custom_dir = _custom_plugins_dir()
    if not custom_dir.is_dir():
        return

    try:
        resolved_dir = custom_dir.resolve()
        dir_info = custom_dir.stat()
    except OSError:
        return

    if not _allow_unsafe_plugins() and (dir_info.st_mode & (stat.S_IWGRP | stat.S_IWOTH)):
        get_logger().warn(
            f"Ignoring plugins in world/group-writable directory: {custom_dir} "
            "(chmod 700 it, or set WOBBLE_ALLOW_UNSAFE_PLUGINS=1)."
        )
        return

    for entry in sorted(custom_dir.iterdir()):
        try:
            plugin_file = entry / "plugin.py"
            if entry.is_symlink() or not entry.is_dir() or entry.name.startswith(("_", ".")):
                continue
            if not plugin_file.is_file():
                continue
            # No symlinked plugin files escaping the plugin directory.
            if plugin_file.is_symlink() or plugin_file.resolve().parent != (resolved_dir / entry.name):
                continue
            if not _allow_unsafe_plugins():
                if not _is_private(entry, kind="dir"):
                    get_logger().warn(f"Ignoring writable-by-others plugin directory: {entry}")
                    continue
                if not _is_private(plugin_file, kind="file"):
                    get_logger().warn(f"Ignoring writable-by-others plugin file: {plugin_file}")
                    continue
            if not _PLUGIN_NAME_RE.match(entry.name):
                get_logger().warn(f"Ignoring plugin directory with unsafe name: {entry.name!r}")
                continue
            _load_user_plugin(entry.name, plugin_file)
        except OSError:
            continue


def _load_user_plugin(name: str, file_path: Path) -> None:
    """Dynamically load one user plugin; failures never crash the core."""
    module_name = f"wobble_user_plugin_{name}"
    try:
        spec = importlib.util.spec_from_file_location(module_name, str(file_path))
        if not (spec and spec.loader):
            return
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        plugin = _register_module(module, allow_override=False)
        if plugin is None:
            get_logger().warn(
                f"User plugin '{name}' did not register (names must be unique and not shadow built-ins)."
            )
    except Exception as exc:
        # Avoid crashing core if a single plugin fails to load.
        get_logger().warn(f"Failed to load plugin at {file_path}: {exc}")
