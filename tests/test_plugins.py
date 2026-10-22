"""
Test plugin discovery, registry, and built-in plugins.
"""

import unittest
from wobble.plugins.loader import list_plugins, get_plugin


class TestPlugins(unittest.TestCase):
    def test_builtin_plugins_discovered(self):
        plugins = list_plugins()
        plugin_names = [p.name for p in plugins]

        expected = ["android", "static_web", "vite", "react", "vue", "svelte", "nextjs", "python_web", "php"]
        for exp in expected:
            self.assertIn(exp, plugin_names)

    def test_plugin_metadata(self):
        android_plugin = get_plugin("android")
        self.assertIsNotNone(android_plugin)
        self.assertEqual(android_plugin.category, "android")

        vite_plugin = get_plugin("vite")
        self.assertIsNotNone(vite_plugin)
        self.assertEqual(vite_plugin.category, "web")
        self.assertIn("node", vite_plugin.required_tools)

    def test_plugin_prerequisites(self):
        static_plugin = get_plugin("static_web")
        self.assertIsNotNone(static_plugin)
        prereq = static_plugin.check_prerequisites()
        self.assertTrue(prereq["ready"])

    def test_plugin_aliases(self):
        self.assertEqual(get_plugin("python").name, "python_web")
        self.assertEqual(get_plugin("flask").name, "python_web")
        self.assertEqual(get_plugin("fastapi").name, "python_web")
        self.assertEqual(get_plugin("static").name, "static_web")
        self.assertEqual(get_plugin("next").name, "nextjs")


if __name__ == "__main__":
    unittest.main()


class TestUserPluginHardening(unittest.TestCase):
    """User plugins are untrusted: private dirs only, no shadowing built-ins."""

    def setUp(self):
        import os
        import tempfile
        from pathlib import Path
        import wobble.plugins.loader as loader

        self.loader = loader
        self.tmp = Path(tempfile.mkdtemp(prefix="wobble_plugins_"))
        self.home = self.tmp / "home"
        self.plugin_root = self.home / ".wobble" / "plugins"
        self.plugin_root.mkdir(parents=True)
        self._old_home = os.environ.get("HOME")
        os.environ["HOME"] = str(self.home)
        self._reset()

    def tearDown(self):
        import os
        import shutil

        self._reset()
        if self._old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self._old_home
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _reset(self):
        self.loader._INITIALIZED = False
        self.loader._PLUGINS_REGISTRY.clear()

    def _write_plugin(self, dir_name, class_name, plugin_name, mode_file=0o600, mode_dir=0o700):
        import os

        directory = self.plugin_root / dir_name
        directory.mkdir()
        (directory / "plugin.py").write_text(
            "from wobble.plugins.base import BasePlugin\n\n"
            f"class {class_name}(BasePlugin):\n"
            f"    name = {plugin_name!r}\n"
            "    category = 'web'\n"
            "    description = 'test plugin'\n\n"
            "    def detect(self, project_path):\n"
            "        return False\n\n"
            "    def create_project(self, name, target_dir, options=None):\n"
            "        return True\n",
            encoding="utf-8",
        )
        os.chmod(directory / "plugin.py", mode_file)
        os.chmod(directory, mode_dir)
        return directory

    def test_private_user_plugin_loads(self):
        self._write_plugin("custom_tool", "CustomToolPlugin", "custom_tool")
        self.assertIsNotNone(self.loader.get_plugin("custom_tool"))

    def test_world_writable_plugin_directory_is_ignored(self):
        self._write_plugin("evil", "EvilPlugin", "evil", mode_dir=0o777)
        self.assertIsNone(self.loader.get_plugin("evil"))

    def test_user_plugin_cannot_shadow_builtin(self):
        self._write_plugin("vite", "FakeVite", "vite")
        plugin = self.loader.get_plugin("vite")
        self.assertIsNotNone(plugin)
        self.assertEqual(plugin.__class__.__name__, "VitePlugin")

    def test_unsafe_plugin_name_is_ignored(self):
        self._write_plugin("badname", "BadPlugin", "Bad-Name")
        self.assertIsNone(self.loader.get_plugin("Bad-Name"))
        self.assertNotIn("Bad-Name", [p.name for p in self.loader.list_plugins()])
