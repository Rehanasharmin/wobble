"""
Test structured JSON outputs for AI agents and automated scripting.
"""

import unittest
import json
import io
from contextlib import redirect_stdout

from wobble.cli import main
from wobble.core.schema import get_cli_schema
from wobble.core.doctor import inspect_environment


class TestJsonOutput(unittest.TestCase):
    def test_schema_valid_json(self):
        schema = get_cli_schema()
        # Verify serialize and deserialize
        serialized = json.dumps(schema)
        deserialized = json.loads(serialized)
        self.assertEqual(deserialized["command"], "wob")
        self.assertIn("create", deserialized["commands"])

    def test_doctor_json_mode(self):
        f = io.StringIO()
        with redirect_stdout(f):
            main(["--json", "doctor"])
        output = f.getvalue().strip()
        data = json.loads(output)
        self.assertIn("status", data)
        self.assertIn("counts", data)
        self.assertIn("checks", data)

    def test_project_list_json(self):
        f = io.StringIO()
        with redirect_stdout(f):
            main(["--json", "project", "list"])
        output = f.getvalue().strip()
        data = json.loads(output)
        self.assertIn("projects", data)

    def test_plugin_list_json(self):
        f = io.StringIO()
        with redirect_stdout(f):
            main(["--json", "plugin", "list"])
        output = f.getvalue().strip()
        data = json.loads(output)
        self.assertIn("plugins", data)
        self.assertGreater(data["count"], 0)


if __name__ == "__main__":
    unittest.main()
