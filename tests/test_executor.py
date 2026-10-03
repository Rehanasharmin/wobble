"""
Test command executor and environment builder.
"""

import os
import unittest
import tempfile
import shutil
from pathlib import Path

from wobble.core.executor import run_command, build_execution_env


class TestExecutor(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="wobble_exec_")
        self.test_path = Path(self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_run_command_success(self):
        res = run_command(["echo", "hello wobble"])
        self.assertTrue(res.success)
        self.assertEqual(res.returncode, 0)
        self.assertIn("hello wobble", res.stdout)

    def test_run_command_relative_executable_in_cwd(self):
        script = self.test_path / "test_script.sh"
        script.write_text("#!/bin/sh\necho 'from relative script'\n")
        script.chmod(0o755)

        # Run with relative executable name from cwd
        res = run_command(["./test_script.sh"], cwd=self.test_path)
        self.assertTrue(res.success)
        self.assertIn("from relative script", res.stdout)

    def test_run_command_missing_executable(self):
        res = run_command(["nonexistent_binary_xyz_12345"])
        self.assertFalse(res.success)
        self.assertEqual(res.returncode, 127)
        self.assertIn("Executable not found", res.stderr)

    def test_build_execution_env(self):
        env = build_execution_env({"CUSTOM_VAR": "WOBBLE_TEST"})
        self.assertEqual(env.get("CUSTOM_VAR"), "WOBBLE_TEST")
        self.assertIn("PATH", env)


if __name__ == "__main__":
    unittest.main()
