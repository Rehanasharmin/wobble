"""
Test project creation, scaffolding, wobble.json validation, and info.
"""

import unittest
import tempfile
import shutil
from pathlib import Path

from wobble.plugins.loader import get_plugin
from wobble.project.spec import ProjectSpec, PROJECT_SPEC_FILENAME
from wobble.project.manager import (
    find_current_project,
    get_project_info,
    register_project,
    unregister_project
)


class TestProject(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="wobble_test_")
        self.test_path = Path(self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_create_android_project(self):
        android_plugin = get_plugin("android")
        self.assertIsNotNone(android_plugin)

        app_dir = self.test_path / "test_android_app"
        success = android_plugin.create_project(
            "test_android_app",
            app_dir,
            {"package": "com.test.wobbleapp"}
        )
        self.assertTrue(success)

        # Check essential Android files exist
        self.assertTrue((app_dir / PROJECT_SPEC_FILENAME).exists())
        self.assertTrue((app_dir / "build.gradle").exists())
        self.assertTrue((app_dir / "settings.gradle").exists())
        self.assertTrue((app_dir / "app" / "build.gradle").exists())
        self.assertTrue((app_dir / "app" / "src" / "main" / "AndroidManifest.xml").exists())
        self.assertTrue((app_dir / "app" / "src" / "main" / "java" / "com" / "test" / "wobbleapp" / "MainActivity.java").exists())

        # Load and verify spec
        spec = ProjectSpec.load_from_dir(app_dir)
        self.assertIsNotNone(spec)
        self.assertEqual(spec.name, "test_android_app")
        self.assertEqual(spec.project_type, "android")
        self.assertEqual(spec.package_id, "com.test.wobbleapp")

    def test_create_static_web_project(self):
        web_plugin = get_plugin("static_web")
        self.assertIsNotNone(web_plugin)

        site_dir = self.test_path / "test_site"
        success = web_plugin.create_project("test_site", site_dir)
        self.assertTrue(success)

        self.assertTrue((site_dir / "index.html").exists())
        self.assertTrue((site_dir / "css" / "style.css").exists())
        self.assertTrue((site_dir / "js" / "app.js").exists())
        self.assertTrue((site_dir / PROJECT_SPEC_FILENAME).exists())

        spec = ProjectSpec.load_from_dir(site_dir)
        self.assertEqual(spec.project_type, "web")
        self.assertEqual(spec.framework, "static_web")

    def test_project_info_and_metrics(self):
        web_plugin = get_plugin("static_web")
        site_dir = self.test_path / "test_metrics_site"
        web_plugin.create_project("test_metrics_site", site_dir)

        info = get_project_info(site_dir)
        self.assertIsNotNone(info)
        self.assertEqual(info["name"], "test_metrics_site")
        self.assertIn("metrics", info)
        self.assertGreater(info["metrics"]["file_count"], 0)


if __name__ == "__main__":
    unittest.main()
