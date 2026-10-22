"""Persistent configuration with strict values and non-destructive recovery."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from wobble.core.context import get_wobble_config_path, get_wobble_home
from wobble.core.errors import ConfigError
from wobble.core.fsutil import atomic_write_json, backup_corrupted_file


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
    "verbose": False,
}

_BOOLEAN_KEYS = {"auto_deps_install", "verbose"}
_TRUE_VALUES = {"true", "1", "yes", "on"}
_FALSE_VALUES = {"false", "0", "no", "off"}
_MISSING = object()


def _coerce_value(key: str, value: Any) -> Any:
    """Validate and coerce known settings before touching in-memory state."""
    if key == "dev_server_port":
        if isinstance(value, bool):
            raise ConfigError(
                "Configuration 'dev_server_port' must be an integer between 1 and 65535.",
                code="invalid_config_value", exit_code=2,
            )
        try:
            port = int(value)
        except (TypeError, ValueError):
            raise ConfigError(
                f"Invalid port {value!r} for 'dev_server_port'.",
                code="invalid_config_value",
                hint="Use an integer from 1 to 65535, for example: wob config set dev_server_port 3000",
                exit_code=2,
            )
        if not 1 <= port <= 65535:
            raise ConfigError(
                f"Port {port} is outside the valid range for 'dev_server_port'.",
                code="invalid_config_value",
                hint="Use an integer from 1 to 65535.",
                exit_code=2,
            )
        return port

    if key in _BOOLEAN_KEYS:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in _TRUE_VALUES:
                return True
            if normalized in _FALSE_VALUES:
                return False
        raise ConfigError(
            f"Invalid boolean {value!r} for '{key}'.",
            code="invalid_config_value",
            hint="Use true/false, yes/no, on/off, or 1/0.",
            exit_code=2,
        )
    return value


class ConfigManager:
    def __init__(self, config_path: Optional[Path] = None) -> None:
        self.config_path = Path(config_path) if config_path is not None else get_wobble_config_path()
        self._config: Dict[str, Any] = {}
        self.warnings: List[str] = []
        self.recovered_from: Optional[Path] = None
        self.load()

    def load(self) -> Dict[str, Any]:
        """Load settings, preserving malformed input before restoring defaults.

        Permission and write errors are not corruption and are never silently
        ignored. They surface as ConfigError so automation cannot mistake an
        unsaved configuration for a successful update.
        """
        self.warnings = []
        self.recovered_from = None
        try:
            with self.config_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, dict):
                raise ValueError("configuration root must be a JSON object")
        except FileNotFoundError:
            self._config = DEFAULT_CONFIG.copy()
            self.save()
            return self._config
        except OSError as exc:
            raise ConfigError(
                f"Cannot read configuration '{self.config_path}': {exc}",
                code="config_read_failed",
                hint="Check the file and parent-directory permissions.",
                details={"path": str(self.config_path)},
            ) from exc
        except (json.JSONDecodeError, UnicodeError, ValueError) as exc:
            try:
                backup = backup_corrupted_file(self.config_path)
            except OSError as backup_error:
                raise ConfigError(
                    f"Configuration is invalid and could not be preserved: {backup_error}",
                    code="config_backup_failed",
                    hint=f"The original was left untouched at {self.config_path}. Restore it manually.",
                    details={"path": str(self.config_path)},
                ) from backup_error
            self._config = DEFAULT_CONFIG.copy()
            self.recovered_from = backup
            self.warnings.append(
                f"Invalid configuration was preserved at '{backup}' and defaults were restored ({exc})."
            )
            self.save()
            return self._config

        self._config = {**DEFAULT_CONFIG, **data}
        return self._config

    def save(self) -> None:
        """Persist settings atomically or raise an actionable ConfigError."""
        try:
            atomic_write_json(self.config_path, self._config)
        except Exception as exc:
            raise ConfigError(
                f"Cannot save configuration '{self.config_path}': {exc}",
                code="config_write_failed",
                hint="Check available disk space and file permissions, then retry.",
                details={"path": str(self.config_path)},
            ) from exc

    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set one value, rolling back memory if the atomic disk write fails."""
        coerced = _coerce_value(key, value)
        previous = self._config.get(key, _MISSING)
        self._config[key] = coerced
        try:
            self.save()
        except ConfigError:
            if previous is _MISSING:
                self._config.pop(key, None)
            else:
                self._config[key] = previous
            raise

    def all(self) -> Dict[str, Any]:
        return self._config.copy()


_config_manager: Optional[ConfigManager] = None


def get_config() -> ConfigManager:
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager
