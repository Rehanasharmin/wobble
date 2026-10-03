"""
Test framework detection rules across various project structures.
"""

import unittest
import tempfile
import shutil
from pathlib import Path

from wobble.plugins.loader import detect_plugin_for_path
from wobble.web.detector import detect_web_framework


class TestFrameworkDetection(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="wobble_detect_")
        self.test_path = Path(self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_detect_android(self):
        d = self.test_path / "android_proj"
        (d / "app").mkdir(parents=True)
        (d / "app" / "build.gradle").write_text("apply plugin: 'com.android.application'")

        plugin = detect_plugin_for_path(d)
        self.assertIsNotNone(plugin)
        self.assertEqual(plugin.name, "android")

    def test_detect_vite(self):
        d = self.test_path / "vite_proj"
        d.mkdir(parents=True)
        (d / "vite.config.js").write_text("export default {}")

        plugin = detect_plugin_for_path(d)
        self.assertIsNotNone(plugin)
        self.assertEqual(plugin.name, "vite")

    def test_detect_react(self):
        d = self.test_path / "react_proj"
        d.mkdir(parents=True)
        (d / "package.json").write_text('{"dependencies": {"react": "^18.0.0"}}')

        plugin = detect_plugin_for_path(d)
        self.assertIsNotNone(plugin)
        self.assertEqual(plugin.name, "react")

    def test_detect_python_web(self):
        d = self.test_path / "py_proj"
        d.mkdir(parents=True)
        (d / "app.py").write_text("import flask")

        plugin = detect_plugin_for_path(d)
        self.assertIsNotNone(plugin)
        self.assertEqual(plugin.name, "python_web")

    def test_detect_php(self):
        d = self.test_path / "php_proj"
        d.mkdir(parents=True)
        (d / "index.php").write_text("<?php phpinfo(); ?>")

        plugin = detect_plugin_for_path(d)
        self.assertIsNotNone(plugin)
        self.assertEqual(plugin.name, "php")


if __name__ == "__main__":
    unittest.main()
