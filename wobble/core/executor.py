"""Safe subprocess execution with actionable, structured failure results.

No shell is involved. Commands use argument arrays, inherit a carefully built
Termux/Android environment, and consistently distinguish missing executables
(127), non-executable files (126), timeouts (124), and interrupts (130).
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from wobble.core.context import (
    get_prefix,
    get_home,
    get_android_sdk_candidates,
    get_java_home_candidates,
)


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _shell_returncode(returncode: int) -> int:
    """Map subprocess' negative signal codes to conventional shell statuses."""
    return 128 - returncode if returncode < 0 else returncode


class ExecutionResult:
    def __init__(
        self,
        command: List[str],
        returncode: int,
        stdout: str,
        stderr: str,
        *,
        error_code: Optional[str] = None,
        hint: Optional[str] = None,
    ) -> None:
        self.command = list(command)
        self.returncode = _shell_returncode(returncode)
        self.stdout = _text(stdout)
        self.stderr = _text(stderr)
        self.success = self.returncode == 0
        self.error_code = None if self.success else (error_code or "command_failed")
        self.hint = None if self.success else hint

    @property
    def error(self) -> Optional[str]:
        """Best available concise failure text for result dictionaries."""
        if self.success:
            return None
        return self.stderr.strip() or self.stdout.strip() or (
            f"Command failed with exit code {self.returncode}."
        )

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "command": " ".join(str(part) for part in self.command),
            "returncode": self.returncode,
            "success": self.success,
            "stdout": self.stdout.strip(),
            "stderr": self.stderr.strip(),
        }
        if not self.success:
            data["error"] = self.error
            data["error_code"] = self.error_code
            if self.hint:
                data["hint"] = self.hint
        return data


def build_execution_env(extra_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Construct an execution environment with comprehensive PATH and Android/Java variables."""
    env = os.environ.copy()

    prefix = str(get_prefix())
    home = str(get_home())
    standard_paths = [
        f"{home}/.local/bin",
        f"{home}/bin",
        f"{prefix}/bin",
        "/system/bin",
        "/system/xbin",
    ]

    current_path = env.get("PATH", "")
    current_items = current_path.split(":") if current_path else []

    merged_paths = []
    for path in standard_paths + current_items:
        if path and path not in merged_paths and os.path.exists(path):
            merged_paths.append(path)

    if "JAVA_HOME" not in env:
        java_candidates = get_java_home_candidates()
        if java_candidates:
            env["JAVA_HOME"] = str(java_candidates[0])
            merged_paths.insert(0, str(java_candidates[0] / "bin"))

    if "ANDROID_HOME" not in env:
        sdk_candidates = get_android_sdk_candidates()
        if sdk_candidates:
            sdk_path = sdk_candidates[0]
            env["ANDROID_HOME"] = str(sdk_path)
            env["ANDROID_SDK_ROOT"] = str(sdk_path)
            for sub in ("cmdline-tools/latest/bin", "cmdline-tools/bin", "platform-tools", "build-tools"):
                sub_path = sdk_path / sub
                if sub_path.exists():
                    merged_paths.insert(0, str(sub_path))

    env["PATH"] = ":".join(merged_paths)
    if extra_env:
        env.update(extra_env)
    return env


def _prepared_error(
    command: List[str], returncode: int, message: str, code: str, hint: Optional[str] = None
) -> ExecutionResult:
    return ExecutionResult(command, returncode, "", message, error_code=code, hint=hint)


def _normalize_command(cmd: Any) -> List[Any]:
    """Turn API input into a list without ever iterating a string as arguments."""
    if cmd is None or isinstance(cmd, (str, bytes)):
        return []
    try:
        return list(cmd)
    except TypeError:
        return [cmd]


def _prepare_command(
    cmd: List[str], cwd: Optional[Path], env: Optional[Dict[str, str]]
) -> Tuple[Optional[List[str]], Dict[str, str], Optional[str], Optional[ExecutionResult]]:
    """Validate input and resolve an executable before starting a process."""
    command = _normalize_command(cmd)
    if not command or not isinstance(command[0], str) or not command[0].strip():
        return None, {}, None, _prepared_error(
            command, 2, "No executable was provided.", "invalid_command",
            "Pass a non-empty command argument array.",
        )
    if any(not isinstance(part, str) for part in command):
        return None, {}, None, _prepared_error(
            command, 2, "Every command argument must be a string.", "invalid_command"
        )
    # Only inspect string contents after the type pass above. Keeping these
    # checks separate makes the non-string fallback explicit and total.
    if any("\x00" in part for part in command):
        return None, {}, None, _prepared_error(
            command, 2, "Command arguments cannot contain NUL bytes.", "invalid_command"
        )

    target_cwd = str(Path(cwd).expanduser()) if cwd is not None else None
    if target_cwd is not None and not Path(target_cwd).is_dir():
        return None, {}, target_cwd, _prepared_error(
            command, 1,
            f"Working directory does not exist or is not a directory: {target_cwd}",
            "invalid_working_directory",
            "Check the project path and try again.",
        )

    exec_env = build_execution_env(env)
    executable = command[0]
    resolved: Optional[str] = None

    # A slash denotes an explicit path, relative to cwd when appropriate.
    if "/" in executable:
        candidate = Path(executable).expanduser()
        if not candidate.is_absolute() and target_cwd:
            candidate = Path(target_cwd) / candidate
        if candidate.is_file():
            resolved = str(candidate.resolve())
            if not os.access(resolved, os.X_OK):
                return None, exec_env, target_cwd, _prepared_error(
                    command, 126,
                    f"Permission denied: '{executable}' is not executable.",
                    "permission_denied",
                    f"Make it executable with: chmod +x {executable}",
                )
    else:
        resolved = shutil.which(executable, path=exec_env.get("PATH"))

    if not resolved:
        return None, exec_env, target_cwd, _prepared_error(
            command, 127,
            f"Executable not found: '{executable}'. Check that it is installed and available in PATH.",
            "executable_not_found",
            "Run 'wob doctor' to identify missing tools and installation commands.",
        )

    return [resolved, *command[1:]], exec_env, target_cwd, None


def run_command(
    cmd: List[str],
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
    timeout: Optional[float] = 300,
    capture_output: bool = True,
) -> ExecutionResult:
    """Execute a command synchronously without raising routine OS failures."""
    command = _normalize_command(cmd)
    try:
        run_cmd, exec_env, target_cwd, error = _prepare_command(command, cwd, env)
    except Exception as exc:
        return _prepared_error(command, 1, f"Could not prepare command: {exc}", "execution_setup_failed")
    if error:
        return error

    try:
        if capture_output:
            proc = subprocess.run(
                run_cmd,
                cwd=target_cwd,
                env=exec_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            return ExecutionResult(command, proc.returncode, proc.stdout, proc.stderr)

        proc = subprocess.run(run_cmd, cwd=target_cwd, env=exec_env, timeout=timeout)
        return ExecutionResult(command, proc.returncode, "", "")
    except subprocess.TimeoutExpired as exc:
        stdout = _text(exc.stdout)
        stderr = _text(exc.stderr).rstrip()
        timeout_message = f"Command timed out after {timeout} seconds."
        stderr = f"{stderr}\n{timeout_message}" if stderr else timeout_message
        return ExecutionResult(
            command, 124, stdout, stderr,
            error_code="timeout",
            hint="Check whether the tool is waiting for input or stuck, then retry.",
        )
    except FileNotFoundError as exc:
        # Covers races where a resolved executable disappears before exec().
        return _prepared_error(
            command, 127, f"Executable not found: '{command[0]}' ({exc}).",
            "executable_not_found", "Run 'wob doctor' to check the tool installation.",
        )
    except PermissionError as exc:
        return _prepared_error(
            command, 126, f"Permission denied executing '{command[0]}': {exc}",
            "permission_denied", "Check the executable and working-directory permissions.",
        )
    except OSError as exc:
        return _prepared_error(
            command, 1, f"Could not execute '{command[0]}': {exc}", "os_error"
        )
    except Exception as exc:
        return _prepared_error(
            command, 1, f"Failed to execute '{command[0]}': {exc}", "execution_failed"
        )


def _terminate_process(proc: subprocess.Popen) -> None:
    """Terminate a child and its process group, escalating if necessary."""
    if proc.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGTERM)
        else:
            proc.terminate()
        proc.wait(timeout=5)
        return
    except (OSError, subprocess.TimeoutExpired):
        pass

    try:
        if proc.poll() is None:
            if os.name == "posix":
                os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()
            proc.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        # There is no safer action left at this boundary; preserve the original
        # interrupt/timeout result rather than masking it with cleanup noise.
        pass


def stream_command_result(
    cmd: List[str],
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
    *,
    capture_output: bool = False,
    timeout: Optional[float] = None,
) -> ExecutionResult:
    """Stream a long-running command, or capture it for clean JSON output.

    Human mode streams in real time. JSON callers pass ``capture_output=True``
    so child output is attached to the result instead of corrupting the JSON
    document. A timeout of ``None`` is intentional for interactive dev servers.
    """
    command = _normalize_command(cmd)
    try:
        run_cmd, exec_env, target_cwd, error = _prepare_command(command, cwd, env)
    except Exception as exc:
        error = _prepared_error(command, 1, f"Could not prepare command: {exc}", "execution_setup_failed")
    if error:
        if not capture_output:
            print(f"Error: {error.stderr}", file=sys.stderr)
        return error

    # redirect_stdout(StringIO) has no fileno. Capture in that case and replay
    # after completion rather than failing with io.UnsupportedOperation.
    replay_output = False
    if capture_output:
        stdout_target = subprocess.PIPE
        stderr_target = subprocess.PIPE
    else:
        try:
            sys.stdout.fileno()
            sys.stderr.fileno()
            stdout_target = sys.stdout
            stderr_target = sys.stderr
        except (AttributeError, OSError, ValueError):
            stdout_target = subprocess.PIPE
            stderr_target = subprocess.PIPE
            replay_output = True

    proc: Optional[subprocess.Popen] = None
    pipes = stdout_target == subprocess.PIPE
    try:
        proc = subprocess.Popen(
            run_cmd,
            cwd=target_cwd,
            env=exec_env,
            stdout=stdout_target,
            stderr=stderr_target,
            text=True,
            encoding="utf-8",
            errors="replace",
            start_new_session=(os.name == "posix"),
        )
        if pipes:
            stdout, stderr = proc.communicate(timeout=timeout)
            returncode = proc.returncode
        else:
            stdout, stderr = "", ""
            returncode = proc.wait(timeout=timeout)

        result = ExecutionResult(command, returncode, stdout, stderr)
        if replay_output:
            if stdout:
                sys.stdout.write(stdout)
            if stderr:
                sys.stderr.write(stderr)
        return result
    except subprocess.TimeoutExpired:
        if proc is not None:
            _terminate_process(proc)
        stdout, stderr = ("", "")
        if proc is not None and pipes:
            stdout, stderr = proc.communicate()
        message = f"Command timed out after {timeout} seconds."
        if not capture_output:
            print(f"Error: {message}", file=sys.stderr)
        return ExecutionResult(
            command, 124, stdout, _text(stderr).rstrip() + ("\n" if stderr else "") + message,
            error_code="timeout",
            hint="Check whether the tool is waiting for input or stuck, then retry.",
        )
    except KeyboardInterrupt:
        if proc is not None:
            _terminate_process(proc)
        if proc is not None and pipes:
            proc.communicate()
        if not capture_output:
            print("\nProcess interrupted by user.", file=sys.stderr)
        return ExecutionResult(
            command, 130, "", "Process interrupted by user.", error_code="interrupted"
        )
    except FileNotFoundError as exc:
        result = _prepared_error(
            command, 127, f"Executable not found: '{command[0]}' ({exc}).", "executable_not_found"
        )
    except PermissionError as exc:
        result = _prepared_error(
            command, 126, f"Permission denied executing '{command[0]}': {exc}", "permission_denied"
        )
    except Exception as exc:
        result = _prepared_error(
            command, 1, f"Failed to execute '{command[0]}': {exc}", "execution_failed"
        )

    if not capture_output:
        print(f"Error: {result.stderr}", file=sys.stderr)
    return result


def stream_command(
    cmd: List[str],
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
) -> int:
    """Backward-compatible integer wrapper around :func:`stream_command_result`."""
    return stream_command_result(cmd, cwd=cwd, env=env).returncode
