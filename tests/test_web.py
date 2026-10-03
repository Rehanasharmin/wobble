"""
Test web preview port discovery, framework detection, and command generation.
"""

import unittest
import tempfile
import shutil
from pathlib import Path

from wobble.web.preview import find_free_port
from wobble.web.detector import detect_web_framework
from wobble.plugins.loader import get_plugin


class TestWeb(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="wobble_web_test_")
        self.test_path = Path(self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_find_free_port(self):
        port = find_free_port(3000)
        self.assertIsInstance(port, int)
        self.assertGreaterEqual(port, 3000)

    def test_detect_static_web(self):
        (self.test_path / "index.html").write_text("<h1>Test</h1>")
        fw = detect_web_framework(self.test_path)
        self.assertEqual(fw, "static_web")

    def test_vite_dev_command(self):
        vite_plugin = get_plugin("vite")
        self.assertIsNotNone(vite_plugin)
        cmd = vite_plugin.get_dev_command(self.test_path, {"port": 4000, "host": "0.0.0.0"})
        self.assertIn("vite", cmd)
        self.assertIn("4000", cmd)
        self.assertIn("0.0.0.0", cmd)

    def test_python_dev_command(self):
        py_plugin = get_plugin("python_web")
        self.assertIsNotNone(py_plugin)
        cmd = py_plugin.get_dev_command(self.test_path)
        self.assertEqual(cmd, ["python3", "app.py"])


if __name__ == "__main__":
    unittest.main()
