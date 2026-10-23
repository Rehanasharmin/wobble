"""Regression tests for actionable errors, exit codes, and JSON failures."""

import io
import json
import os
import shutil
import socket
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from wobble.android.apk import inspect_apk
from wobble.bootstrap import run as bootstrap_run
from wobble.cli import _hoist_global_flags, main
from wobble.core.config import ConfigManager
from wobble.core.errors import ConfigError, PreviewError, ProjectSpecError, RegistryError
from wobble.core.executor import run_command, stream_command_result
from wobble.core.logger import Logger, get_logger, set_logger
from wobble.deps.manager import _run_dependency_command, deps_install, deps_list
from wobble.project.manager import register_project
from wobble.project.spec import ProjectSpec
from wobble.web.preview import start_static_preview


def invoke(argv):
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


class TestCLIErrorContracts(unittest.TestCase):
    def test_invalid_arguments_are_json_and_exit_2(self):
        code, stdout, stderr = invoke(["web", "dev", "--port", "not-a-port", "--json"])
        self.assertEqual(code, 2)
        self.assertEqual(stderr, "")
        data = json.loads(stdout)
        self.assertFalse(data["success"])
        self.assertEqual(data["error_code"], "invalid_arguments")
        self.assertIn("usage", data["details"])
        self.assertIn("hint", data)

    def test_global_hoisting_does_not_steal_option_values(self):
        for argv in (
            ["create", "web", "site", "--framework", "-v"],
            ["create", "web", "site", "--dir", "--json"],
            ["web", "dev", "--host", "--verbose"],
        ):
            with self.subTest(argv=argv):
                self.assertEqual(_hoist_global_flags(argv), argv)

        argv = ["create", "web", "site", "--framework", "vite", "--json"]
        self.assertEqual(_hoist_global_flags(argv), ["--json", *argv[:-1]])

        # --json is the attempted --dir value here, not an output-mode flag.
        code, stdout, stderr = invoke(["create", "web", "site", "--dir", "--json"])
        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("usage:", stderr)

    def test_out_of_range_port_has_human_usage_error(self):
        code, stdout, stderr = invoke(["preview", "--port", "70000"])
        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("usage:", stderr)
        self.assertIn("1 and 65535", stderr)
        self.assertIn("Hint:", stderr)

    def test_handler_failure_still_emits_json(self):
        code, stdout, stderr = invoke(["create", "web", "../invalid", "--json"])
        self.assertEqual(code, 1)
        self.assertEqual(stderr, "")
        data = json.loads(stdout)
        self.assertFalse(data["success"])
        self.assertEqual(data["error_code"], "command_failed")
        self.assertIn("Invalid project name", data["error"])

    def test_unexpected_error_has_stable_json_and_no_traceback_by_default(self):
        with patch("wobble.cli._dispatch", side_effect=RuntimeError("test boom")):
            code, stdout, stderr = invoke(["--json", "banner"])
        self.assertEqual(code, 1)
        self.assertEqual(stderr, "")
        data = json.loads(stdout)
        self.assertEqual(data["error_code"], "internal_error")
        self.assertIn("test boom", data["error"])
        self.assertNotIn("Traceback", stdout + stderr)

    def test_verbose_unexpected_error_includes_diagnostic_context(self):
        with patch("wobble.cli._dispatch", side_effect=RuntimeError("verbose boom")):
            code, stdout, stderr = invoke(["--json", "--verbose", "banner"])
        self.assertEqual(code, 1)
        self.assertIn("Traceback", stderr)
        data = json.loads(stdout)
        self.assertEqual(data["details"]["exception"], "RuntimeError")

    def test_keyboard_interrupt_has_exit_130_and_json(self):
        with patch("wobble.cli._dispatch", side_effect=KeyboardInterrupt):
            code, stdout, stderr = invoke(["--json", "banner"])
        self.assertEqual(code, 130)
        self.assertEqual(stderr, "")
        self.assertEqual(json.loads(stdout)["error_code"], "interrupted")

    def test_web_build_reports_elapsed_time_instead_of_name_error(self):
        with patch("wobble.web.manager.run_web_build", return_value={"success": True}):
            code, stdout, stderr = invoke(["web", "build", "--json"])
        self.assertEqual(code, 0, stderr)
        self.assertIn("elapsed_seconds", json.loads(stdout))

    def test_top_level_dev_defaults_to_localhost(self):
        with patch("wobble.web.manager.run_web_dev", return_value=0) as run_dev:
            code, stdout, stderr = invoke(["dev"])
        self.assertEqual(code, 0, stderr)
        self.assertEqual(run_dev.call_args.kwargs["host"], "127.0.0.1")

    def test_legacy_failure_result_gets_stable_error_code(self):
        with patch(
            "wobble.web.manager.run_web_build",
            return_value={"success": False, "error": "missing build tool"},
        ):
            code, stdout, stderr = invoke(["web", "build", "--json"])
        self.assertEqual(code, 1)
        self.assertEqual(stderr, "")
        self.assertEqual(json.loads(stdout)["error_code"], "command_failed")

    def test_bootstrap_fast_paths_use_the_same_error_boundary(self):
        with patch("wobble.bootstrap.print_landing", side_effect=BrokenPipeError):
            self.assertEqual(bootstrap_run([]), 0)

        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("wobble.bootstrap.print_landing", side_effect=RuntimeError("landing failed")):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = bootstrap_run([])
        self.assertEqual(code, 1)
        self.assertIn("Unexpected error: landing failed", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("wobble.bootstrap.maybe_handle_fast_path", side_effect=RuntimeError("fast failed")):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = bootstrap_run(["--version", "--json"])
        self.assertEqual(code, 1)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(json.loads(stdout.getvalue())["error_code"], "internal_error")


class TestExecutorFailures(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="wobble_errors_exec_"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_empty_and_absolute_missing_commands_are_distinguished(self):
        empty = run_command([])
        self.assertEqual(empty.returncode, 2)
        self.assertEqual(empty.error_code, "invalid_command")

        missing = run_command([str(self.root / "missing")])
        self.assertEqual(missing.returncode, 127)
        self.assertEqual(missing.error_code, "executable_not_found")
        self.assertIn("wob doctor", missing.hint)

    def test_non_executable_file_returns_126(self):
        script = self.root / "not-executable.sh"
        script.write_text("#!/bin/sh\necho no\n")
        script.chmod(0o644)
        result = run_command([str(script)])
        self.assertEqual(result.returncode, 126)
        self.assertEqual(result.error_code, "permission_denied")
        self.assertIn("chmod +x", result.hint)

    def test_invalid_working_directory_is_actionable(self):
        result = run_command(["python3", "--version"], cwd=self.root / "missing")
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "invalid_working_directory")
        self.assertIn("Working directory", result.stderr)

    def test_non_string_command_input_returns_an_error_result(self):
        for command in (["python3", object()], ["python3", None], 42, "python3 --version"):
            with self.subTest(command=command):
                result = run_command(command)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.error_code, "invalid_command")
                self.assertIn("error", result.to_dict())

        streamed = stream_command_result(["python3", object()], capture_output=True)
        self.assertEqual(streamed.returncode, 2)
        self.assertEqual(streamed.error_code, "invalid_command")

    def test_timeout_preserves_partial_output_and_returns_124(self):
        result = run_command(
            ["python3", "-c", "import time; print('before timeout', flush=True); time.sleep(5)"],
            timeout=0.05,
        )
        self.assertEqual(result.returncode, 124)
        self.assertEqual(result.error_code, "timeout")
        self.assertIn("before timeout", result.stdout)
        self.assertIn("timed out", result.stderr)

    def test_stream_capture_keeps_child_output_out_of_json_stream(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = stream_command_result(
                ["python3", "-c", "print('child diagnostic')"], capture_output=True
            )
        self.assertTrue(result.success)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(result.stdout.strip(), "child diagnostic")

    def test_stream_capture_replaces_invalid_utf8(self):
        result = stream_command_result(
            ["python3", "-c", "import sys; sys.stdout.buffer.write(b'\\xff')"],
            capture_output=True,
        )
        self.assertTrue(result.success)
        self.assertEqual(result.stdout, "\ufffd")

    def test_dependency_json_helper_captures_child_output(self):
        previous = get_logger()
        set_logger(Logger(json_mode=True))
        stdout = io.StringIO()
        try:
            with redirect_stdout(stdout):
                result = _run_dependency_command(
                    ["python3", "-c", "print('package manager output')"], manager="test"
                )
        finally:
            set_logger(previous)
        self.assertTrue(result["success"])
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(result["stdout"], "package manager output")


class TestPersistenceFailures(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="wobble_errors_state_"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_config_rejects_invalid_values_without_mutating_state(self):
        manager = ConfigManager(self.root / "config.json")
        original = manager.get("dev_server_port")
        with self.assertRaises(ConfigError) as caught:
            manager.set("dev_server_port", "70000")
        self.assertEqual(caught.exception.exit_code, 2)
        self.assertEqual(manager.get("dev_server_port"), original)

        with self.assertRaises(ConfigError):
            manager.set("verbose", "perhaps")
        self.assertFalse(manager.get("verbose"))

    def test_config_write_failure_rolls_back_memory(self):
        path = self.root / "config.json"
        manager = ConfigManager(path)
        before = path.read_bytes()
        with patch("wobble.core.config.atomic_write_json", side_effect=OSError("disk full")):
            with self.assertRaises(ConfigError) as caught:
                manager.set("dev_server_port", 4321)
        self.assertEqual(caught.exception.code, "config_write_failed")
        self.assertEqual(manager.get("dev_server_port"), 3000)
        self.assertEqual(path.read_bytes(), before)

    def test_corruption_recovery_does_not_overwrite_previous_backup(self):
        path = self.root / "config.json"
        path.write_text("{new broken")
        old_backup = self.root / "config.json.corrupt.bak"
        old_backup.write_text("older user data")
        manager = ConfigManager(path)
        self.assertEqual(old_backup.read_text(), "older user data")
        self.assertEqual(manager.recovered_from, self.root / "config.json.corrupt.bak.1")
        self.assertEqual(manager.recovered_from.read_text(), "{new broken")

    def test_registry_write_failure_is_not_silent(self):
        registry = self.root / "projects.json"
        with patch("wobble.project.manager.PROJECT_REGISTRY_FILE", registry), \
             patch("wobble.project.manager.atomic_write_json", side_effect=OSError("read only")):
            with self.assertRaises(RegistryError) as caught:
                register_project("demo", self.root)
        self.assertEqual(caught.exception.code, "registry_write_failed")

    def test_malformed_project_spec_is_not_reported_as_missing(self):
        project = self.root / "broken-project"
        project.mkdir()
        (project / "wobble.json").write_text("{broken")
        with self.assertRaises(ProjectSpecError) as caught:
            ProjectSpec.load_from_dir(project, strict=True)
        self.assertIn("wobble.json", caught.exception.details["path"])

    def test_malformed_dependency_manifest_is_returned_as_an_error(self):
        (self.root / "package.json").write_text("{broken")
        result = deps_list(self.root)
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "dependency_file_invalid")
        self.assertEqual(len(result["errors"]), 1)

    def test_unknown_dependency_stack_fails_with_choices(self):
        result = deps_install("unknown-stack", self.root)
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "unknown_dependency_stack")
        self.assertIn("android, android-sdk, node, python, or php", result["hint"])


class TestOperationalFailureStatus(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="wobble_errors_ops_"))
        self.old_cwd = os.getcwd()
        os.chdir(self.root)

    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.root, ignore_errors=True)

    def test_invalid_apk_returns_failure_instead_of_success(self):
        apk = self.root / "broken.apk"
        apk.write_bytes(b"not a zip")
        direct = inspect_apk(apk)
        self.assertFalse(direct["success"])
        self.assertEqual(direct["error_code"], "invalid_apk_archive")

        code, stdout, stderr = invoke(["apk", "info", str(apk), "--json"])
        self.assertEqual(code, 1)
        self.assertEqual(stderr, "")
        self.assertEqual(json.loads(stdout)["error_code"], "invalid_apk_archive")

    def test_missing_preview_directory_raises_actionable_error(self):
        with self.assertRaises(PreviewError) as caught:
            start_static_preview(self.root / "missing")
        self.assertEqual(caught.exception.code, "preview_directory_not_found")

        code, stdout, stderr = invoke(["web", "preview", "--dir", "also-missing", "--json"])
        self.assertEqual(code, 1)
        self.assertEqual(stderr, "")
        self.assertEqual(json.loads(stdout)["error_code"], "preview_directory_not_found")

    def test_preview_port_collision_is_not_a_successful_exit(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            port = listener.getsockname()[1]
            with self.assertRaises(PreviewError) as caught:
                start_static_preview(self.root, port=port, host="127.0.0.1")
        self.assertEqual(caught.exception.code, "port_in_use")
        self.assertIn("--port", caught.exception.hint)

    def test_apk_operation_failures_print_recovery_hints(self):
        apk = self.root / "demo.apk"
        apk.write_bytes(b"placeholder")
        operations = (
            ("install", "wobble.android.apk.install_apk"),
            ("share", "wobble.android.apk.share_apk"),
            ("sign", "wobble.android.apk.sign_apk"),
        )
        for operation, target in operations:
            with self.subTest(operation=operation):
                with patch(target, return_value={
                    "success": False,
                    "error": "operation denied for test",
                    "hint": "Use the documented recovery step",
                }):
                    code, stdout, stderr = invoke(["apk", operation, str(apk)])
                self.assertEqual(code, 1)
                self.assertIn("operation denied", stderr)
                self.assertIn("Hint: Use the documented recovery step", stdout)

    def test_partial_clean_reports_failed_paths_and_exit_1(self):
        build = self.root / "build"
        build.mkdir()
        (build / "artifact.txt").write_text("keep me")
        with patch("shutil.rmtree", side_effect=OSError("permission denied for test")):
            code, stdout, stderr = invoke(["clean", "--json"])
        self.assertEqual(code, 1)
        self.assertTrue(build.exists())
        data = json.loads(stdout)
        self.assertFalse(data["success"])
        self.assertEqual(data["error_code"], "clean_partial")
        self.assertEqual(data["failed"], 1)
        self.assertIn("permission denied", data["errors"][0]["error"])

    def test_project_creation_survives_registry_failure_with_warning(self):
        from wobble.core.errors import RegistryError as ExpectedRegistryError

        with patch(
            "wobble.project.manager.register_project",
            side_effect=ExpectedRegistryError("registry unavailable for test"),
        ):
            code, stdout, stderr = invoke([
                "create", "web", "registry-warning-demo", "--framework", "static", "--json"
            ])
        self.assertEqual(code, 0, stderr)
        data = json.loads(stdout)
        self.assertTrue(data["success"])
        self.assertFalse(data["registered"])
        self.assertIn("registry unavailable", data["warnings"][0])
        self.assertTrue((self.root / "registry-warning-demo" / "wobble.json").exists())


if __name__ == "__main__":
    unittest.main()
