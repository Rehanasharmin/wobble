"""Shared, actionable errors and machine-readable failure payloads.

Expected operational failures should raise :class:`WobbleError` (or one of its
subclasses) instead of being printed and then forgotten.  The CLI boundary turns
these exceptions into a useful human message or a stable JSON error object and
uses the exception's exit code.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


EXIT_FAILURE = 1
EXIT_USAGE = 2
EXIT_INTERRUPTED = 130


class WobbleError(RuntimeError):
    """An expected failure with a safe message and an optional recovery hint."""

    default_code = "wobble_error"
    default_exit_code = EXIT_FAILURE

    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        hint: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        exit_code: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.message = str(message)
        self.code = code or self.default_code
        self.hint = hint
        self.details = details or {}
        self.exit_code = self.default_exit_code if exit_code is None else exit_code

    def to_dict(self) -> Dict[str, Any]:
        """Return the common JSON error contract used at CLI boundaries."""
        payload: Dict[str, Any] = {
            "success": False,
            "error": self.message,
            "error_code": self.code,
        }
        if self.hint:
            payload["hint"] = self.hint
        if self.details:
            payload["details"] = self.details
        return payload


class UsageError(WobbleError):
    """Invalid command-line input; conventionally exits with status 2."""

    default_code = "invalid_arguments"
    default_exit_code = EXIT_USAGE


class ConfigError(WobbleError):
    default_code = "config_error"


class RegistryError(WobbleError):
    default_code = "registry_error"


class ProjectSpecError(WobbleError):
    default_code = "invalid_project_spec"


class PreviewError(WobbleError):
    default_code = "preview_error"


def unexpected_error_payload(exc: BaseException, verbose: bool = False) -> Dict[str, Any]:
    """Build a JSON-safe unexpected-error response without a traceback by default."""
    error = WobbleError(
        f"Unexpected error: {exc}",
        code="internal_error",
        hint="Run the command again with --verbose for a traceback, or run 'wob doctor'.",
        details={"exception": type(exc).__name__} if verbose else None,
    )
    return error.to_dict()
