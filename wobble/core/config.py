"""
Wobble Configuration System
Manages persistent user settings in ~/.config/wobble/config.json.
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional
from wobble.core.context import get_wobble_config_path, get_wobble_home

DEFAULT_CONFIG: Dict[str, Any] = {
    "version": "1.0",
    "default_author": "Termux Developer",
    "default_web_framework": "vite",
    "default_android_package": "com.example.wobbleapp",
    "dev_server_host": "0.0.0.0",
    "dev_server_port": 3000,
    "custom_plugins_dir": str(get_wobble_home() / "plugins"),
    "sdk_path": "",
    "java_home": "",
    "auto_deps_install": False,
    "verbose": False
}


class ConfigManager:
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or get_wobble_config_path()
        self._config: Dict[str, Any] = {}
        self.load()

    def load(self) -> Dict[str, Any]:
        """Load configuration from disk, falling back to defaults."""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._config = {**DEFAULT_CONFIG, **data}
            except Exception:
                self._config = DEFAULT_CONFIG.copy()
        else:
            self._config = DEFAULT_CONFIG.copy()
            self.save()
        return self._config

    def save(self):
        """Save current configuration to disk."""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=2)
        except Exception as e:
            pass

    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    def set(self, key: str, value: Any):
        # Type coercion for common settings
        if key in ("dev_server_port",):
            try:
                value = int(value)
            except ValueError:
                pass
        elif key in ("auto_deps_install", "verbose"):
            if isinstance(value, str):
                value = value.lower() in ("true", "1", "yes")

        self._config[key] = value
        self.save()

    def all(self) -> Dict[str, Any]:
        return self._config.copy()


_config_manager: Optional[ConfigManager] = None


def get_config() -> ConfigManager:
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager
