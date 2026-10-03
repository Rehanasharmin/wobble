"""
Test unified dependency management and manager resolution.
"""

import unittest
import tempfile
import shutil
from pathlib import Path

from wobble.deps.manager import resolve_package_manager, deps_doctor, deps_list


class TestDeps(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="wobble_deps_")
        self.test_path = Path(self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_resolve_npm(self):
        (self.test_path / "package.json").write_text("{}")
        mgr = resolve_package_manager(self.test_path)
        self.assertEqual(mgr, "npm")

    def test_resolve_pip(self):
        (self.test_path / "requirements.txt").write_text("flask")
        mgr = resolve_package_manager(self.test_path)
        self.assertEqual(mgr, "pip")

    def test_resolve_composer(self):
        (self.test_path / "composer.json").write_text("{}")
        mgr = resolve_package_manager(self.test_path)
        self.assertEqual(mgr, "composer")

    def test_resolve_termux_default(self):
        empty_dir = self.test_path / "empty"
        empty_dir.mkdir()
        mgr = resolve_package_manager(empty_dir)
        self.assertEqual(mgr, "termux")

    def test_deps_doctor_detects_missing_node_modules(self):
        (self.test_path / "package.json").write_text("{}")
        report = deps_doctor(self.test_path)
        self.assertEqual(report["status"], "needs_attention")
        issue_types = [i["type"] for i in report["issues"]]
        self.assertIn("missing_node_modules", issue_types)

    def test_deps_list(self):
        import json
        pkg_data = {"dependencies": {"react": "^18.0.0"}, "devDependencies": {"vite": "^5.0.0"}}
        (self.test_path / "package.json").write_text(json.dumps(pkg_data))
        res = deps_list(self.test_path)
        self.assertEqual(res["dependencies"].get("react"), "^18.0.0")
        self.assertEqual(res["dev_dependencies"].get("vite"), "^5.0.0")


if __name__ == "__main__":
    unittest.main()
