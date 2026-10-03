"""
Test machine-readable schema generation for AI agents.
"""

import unittest
from wobble.core.schema import get_cli_schema


class TestSchema(unittest.TestCase):
    def test_schema_structure(self):
        schema = get_cli_schema()
        self.assertIn("title", schema)
        self.assertIn("version", schema)
        self.assertEqual(schema["command"], "wob")
        self.assertIn("commands", schema)
        self.assertIn("capabilities", schema)
        self.assertIn("environment", schema)

    def test_schema_commands(self):
        schema = get_cli_schema()
        cmds = schema["commands"]
        for required_cmd in ["create", "project", "android", "web", "apk", "deps", "doctor", "plugin", "config", "clean"]:
            self.assertIn(required_cmd, cmds)

    def test_schema_capabilities(self):
        schema = get_cli_schema()
        caps = schema["capabilities"]
        self.assertTrue(caps["termux_native"])
        self.assertFalse(caps["root_required"])
        self.assertFalse(caps["adb_required"])
        self.assertIn("android", caps["supported_frameworks"])
        self.assertIn("vite", caps["supported_frameworks"])


if __name__ == "__main__":
    unittest.main()
