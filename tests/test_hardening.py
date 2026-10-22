"""Regression tests for input validation and destructive-operation safety."""

import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import wobble.android.apk as apk_module
from wobble.cli import _PACKAGE_RE, _validate_project_name, main
from wobble.core.executor import build_execution_env, run_command, stream_command


class TestNameValidation(unittest.TestCase):
    def test_accepts_safe_names(self):
        for name in ("myapp", "my-app", "my_app", "app2", "v1.2.3"):
            self.assertEqual(_validate_project_name(name), name)

    def test_rejects_template_injection(self):
        for name in ('x"><script>', "a&b", "a'b", 'a"b', "a<b", "a>b",
                     "../evil", "..", ".", "-flag", "name with space",
                     "x" * 65, "a/b", "a\\b"):
            with self.assertRaises(ValueError, msg=name):
                _validate_project_name(name)

    def test_package_regex(self):
        self.assertTrue(_PACKAGE_RE.match("com.example.myapp"))
        self.assertTrue(_PACKAGE_RE.match("io.github.user.app_2"))
        for bad in ("com", "1com.example", "com..example",
                    'com.example"; rm -rf', "com/example"):
            self.assertIsNone(_PACKAGE_RE.match(bad), bad)


class TestCreateSafety(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="wobble_hardening_"))
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp)

    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, argv):
        f = io.StringIO()
        with redirect_stdout(f):
            code = main(argv)
        return code, f.getvalue()

    def test_malicious_name_is_rejected_and_nothing_created(self):
        code, _ = self._run(["create", "web", 'x"><script>'])
        self.assertEqual(code, 1)
        self.assertEqual(list(self.tmp.iterdir()), [])

    def test_malicious_package_is_rejected(self):
        code, _ = self._run([
            "create", "android", "safeapp", "--package", 'com.example"; rm -rf /',
        ])
        self.assertEqual(code, 1)
        self.assertEqual(list(self.tmp.iterdir()), [])

    def test_symlink_target_is_refused(self):
        real = self.tmp / "real"
        real.mkdir()
        link = self.tmp / "link"
        link.symlink_to(real)
        code, _ = self._run(["create", "web", "demo", "-d", str(link)])
        self.assertEqual(code, 1)
        self.assertFalse((real / "wobble.json").exists())


class TestCleanSymlinkSafety(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="wobble_clean_symlink_"))
        self.outside = Path(tempfile.mkdtemp(prefix="wobble_outside_"))
        (self.outside / "keep.txt").write_text("must survive")
        (self.tmp / "build").symlink_to(self.outside)
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp)

    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)
        shutil.rmtree(self.outside, ignore_errors=True)

    def test_clean_does_not_follow_symlinked_build_dir(self):
        f = io.StringIO()
        with redirect_stdout(f):
            code = main(["--json", "clean", "--all", "--yes"])
        self.assertEqual(code, 0)
        self.assertTrue((self.outside / "keep.txt").exists())
        self.assertTrue((self.tmp / "build").is_symlink())


class TestExecutionEnv(unittest.TestCase):
    """Subprocess environment injection must work without mutating os.environ."""

    def test_run_command_env_is_injected(self):
        result = run_command(
            ["python3", "-c", "import os; print(os.environ.get('WOBBLE_TEST_ENV', ''))"],
            env={"WOBBLE_TEST_ENV": "sentinel"},
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "sentinel")
        self.assertNotIn("WOBBLE_TEST_ENV", os.environ)

    def test_stream_command_env_is_injected(self):
        # stream_command wires the child to the real stdout, so the child writes
        # its observation to a file instead of stdout.
        tmp = Path(tempfile.mkdtemp(prefix="wobble_stream_env_"))
        marker = tmp / "marker.txt"
        try:
            code = stream_command(
                ["python3", "-c",
                 "import os, pathlib, sys; "
                 "pathlib.Path(sys.argv[1]).write_text(os.environ.get('WOBBLE_STREAM_ENV', ''))",
                 str(marker)],
                env={"WOBBLE_STREAM_ENV": "streamed"},
            )
            self.assertEqual(code, 0)
            self.assertEqual(marker.read_text(), "streamed")
            self.assertNotIn("WOBBLE_STREAM_ENV", os.environ)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_build_execution_env_keeps_path_and_extra(self):
        env = build_execution_env({"PORT": "4321"})
        self.assertEqual(env["PORT"], "4321")
        self.assertTrue(env.get("PATH"))
        self.assertIn("PATH", env)


class TestKeystorePassword(unittest.TestCase):
    def test_password_uses_env_not_argv(self):
        tmp = Path(tempfile.mkdtemp(prefix="wobble_sign_"))
        apk = tmp / "demo.apk"
        apk.write_bytes(b"PK\x03\x04")
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = list(cmd)
            captured["env"] = dict(kwargs.get("env") or {})
            return SimpleNamespace(success=True, stdout="", stderr="", returncode=0)

        try:
            with patch.object(apk_module, "find_tool", return_value="/usr/bin/apksigner"), \
                 patch.object(apk_module, "run_command", side_effect=fake_run), \
                 patch.dict(os.environ, {"WOBBLE_KS_PASS": "s3cret"}):
                result = apk_module.sign_apk(
                    apk, keystore=tmp / "release.jks", key_alias="release")
            self.assertTrue(result["success"])
            joined = " ".join(captured["cmd"])
            self.assertNotIn("s3cret", joined)
            self.assertIn("env:WOBBLE_KS_PASS", joined)
            self.assertEqual(captured["env"].get("WOBBLE_KS_PASS"), "s3cret")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
