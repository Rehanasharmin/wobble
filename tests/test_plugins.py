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


if __name__ == "__main__":
    unittest.main()
