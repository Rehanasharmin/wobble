"""
Wobble Command Executor
Safely runs external tools, manages environment variables, enforces timeouts, and streams output.
"""

import os
import sys
import subprocess
import shutil
from typing import List, Dict, Optional, Tuple, Any
from pathlib import Path
from wobble.core.context import get_prefix, get_home, get_android_sdk_candidates, get_java_home_candidates


class ExecutionResult:
    def __init__(self, command: List[str], returncode: int, stdout: str, stderr: str):
        self.command = command
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.success = (returncode == 0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "command": " ".join(self.command),
            "returncode": self.returncode,
            "success": self.success,
            "stdout": self.stdout.strip(),
            "stderr": self.stderr.strip()
        }


def build_execution_env(extra_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Construct an execution environment with comprehensive PATH and Android/Java variables."""
    env = os.environ.copy()

    # Ensure Termux paths are in PATH
    prefix = str(get_prefix())
    home = str(get_home())
    standard_paths = [
        f"{home}/.local/bin",
        f"{home}/bin",
        f"{prefix}/bin",
        "/system/bin",
        "/system/xbin"
    ]

    current_path = env.get("PATH", "")
    current_items = current_path.split(":") if current_path else []

    merged_paths = []
    for p in standard_paths + current_items:
        if p and p not in merged_paths and os.path.exists(p):
            merged_paths.append(p)

    # Detect & configure JAVA_HOME if not already set
    if "JAVA_HOME" not in env:
        java_candidates = get_java_home_candidates()
        if java_candidates:
            env["JAVA_HOME"] = str(java_candidates[0])
            merged_paths.insert(0, str(java_candidates[0] / "bin"))

    # Detect & configure ANDROID_HOME if not already set
    if "ANDROID_HOME" not in env:
        sdk_candidates = get_android_sdk_candidates()
        if sdk_candidates:
            sdk_path = sdk_candidates[0]
            env["ANDROID_HOME"] = str(sdk_path)
            env["ANDROID_SDK_ROOT"] = str(sdk_path)
            for sub in ["cmdline-tools/latest/bin", "cmdline-tools/bin", "platform-tools", "build-tools"]:
                sub_p = sdk_path / sub
                if sub_p.exists():
                    merged_paths.insert(0, str(sub_p))

    env["PATH"] = ":".join(merged_paths)

    if extra_env:
        env.update(extra_env)

    return env


def run_command(
    cmd: List[str],
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
    timeout: Optional[int] = 300,
    capture_output: bool = True
) -> ExecutionResult:
    """
    Execute a command synchronously with error handling and environment injection.
    """
    exec_env = build_execution_env(env)
    target_cwd = str(cwd) if cwd else None

    # Verify binary exists
    executable = cmd[0]
    resolved = shutil.which(executable, path=exec_env.get("PATH"))
    if not resolved and not os.path.isabs(executable):
        return ExecutionResult(
            command=cmd,
            returncode=127,
            stdout="",
            stderr=f"Executable not found: '{executable}'. Please check that it is installed in PATH."
        )

    try:
        if capture_output:
            proc = subprocess.run(
                cmd,
                cwd=target_cwd,
                env=exec_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout
            )
            return ExecutionResult(cmd, proc.returncode, proc.stdout, proc.stderr)
        else:
            proc = subprocess.run(
                cmd,
                cwd=target_cwd,
                env=exec_env,
                timeout=timeout
            )
            return ExecutionResult(cmd, proc.returncode, "", "")
    except subprocess.TimeoutExpired as e:
        return ExecutionResult(
            command=cmd,
            returncode=124,
            stdout=e.stdout or "" if isinstance(e.stdout, str) else "",
            stderr=f"Command timed out after {timeout} seconds"
        )
    except PermissionError as e:
        return ExecutionResult(
            command=cmd,
            returncode=126,
            stdout="",
            stderr=f"Permission denied executing '{executable}': {e}"
        )
    except Exception as e:
        return ExecutionResult(
            command=cmd,
            returncode=1,
            stdout="",
            stderr=f"Failed to execute command: {e}"
        )


def stream_command(
    cmd: List[str],
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None
) -> int:
    """
    Execute a command while streaming output in real-time to stdout/stderr.
    Useful for interactive dev servers, package installs, and builds.
    """
    exec_env = build_execution_env(env)
    target_cwd = str(cwd) if cwd else None

    executable = cmd[0]
    resolved = shutil.which(executable, path=exec_env.get("PATH"))
    if not resolved and not os.path.isabs(executable):
        print(f"Error: Executable '{executable}' not found in PATH.", file=sys.stderr)
        return 127

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=target_cwd,
            env=exec_env,
            stdout=sys.stdout,
            stderr=sys.stderr
        )
        return proc.wait()
    except KeyboardInterrupt:
        print("\nProcess interrupted by user.")
        return 130
    except Exception as e:
        print(f"Error running '{' '.join(cmd)}': {e}", file=sys.stderr)
        return 1
