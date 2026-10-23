"""
Test user-experience features: shell completion, name suggestions, and clean.
"""

import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from wobble.cli import main, _suggest_names
from wobble.core.schema import get_cli_schema


class TestSuggestions(unittest.TestCase):
    def test_suggest_close_match(self):
        hint = _suggest_names("reacts", ["react", "vue", "svelte"])
        self.assertIn("react", hint)
        self.assertIn("Did you mean", hint)

    def test_suggest_no_match(self):
        hint = _suggest_names("zzzzzz", ["react", "vue"])
        self.assertEqual(hint, "")

    def test_create_unknown_framework_fails_with_hint(self):
        f = io.StringIO()
        with redirect_stdout(f):
            code = main(["create", "web", "demo_ux_app", "-f", "reacts"])
        self.assertEqual(code, 1)

    def test_create_rejects_path_like_names(self):
        f = io.StringIO()
        with redirect_stdout(f):
            code = main(["create", "web", "../evil"])
        self.assertEqual(code, 1)


class TestCompletion(unittest.TestCase):
    def test_bash_completion_script(self):
        f = io.StringIO()
        with redirect_stdout(f):
            code = main(["completion", "bash"])
        self.assertEqual(code, 0)
        script = f.getvalue()
        self.assertTrue(script.startswith("# Wobble (wob) bash completion"))
        self.assertNotIn("\\", script.splitlines()[0])
        self.assertIn("complete -F _wob_completions wob", script)
        for word in ("doctor", "apk", "preview", "completion"):
            self.assertIn(word, script)

    def test_zsh_completion_script(self):
        f = io.StringIO()
        with redirect_stdout(f):
            code = main(["completion", "zsh"])
        self.assertEqual(code, 0)
        script = f.getvalue()
        self.assertIn("#compdef wob", script)
        self.assertIn("_wob", script)

    def test_completion_json_mode(self):
        f = io.StringIO()
        with redirect_stdout(f):
            code = main(["--json", "completion", "bash"])
        self.assertEqual(code, 0)
        data = json.loads(f.getvalue())
        self.assertEqual(data["shell"], "bash")
        self.assertIn("complete", data["script"])

    def test_schema_lists_version_and_help(self):
        schema = get_cli_schema()
        self.assertIn("version", schema["commands"])
        self.assertIn("help", schema["commands"])

    def test_schema_lists_completion(self):
        schema = get_cli_schema()
        self.assertIn("completion", schema["commands"])
        self.assertIn("--yes", [fl["name"] for fl in schema["commands"]["clean"]["flags"]])


class TestHelpLayout(unittest.TestCase):
    def _capture(self, argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(argv)
        return code, buf.getvalue()

    def test_root_help_is_grouped(self):
        from wobble.cli import build_parser
        text = build_parser().format_help()
        for group in ("Projects", "Current project", "Android", "Wobble", "Info"):
            self.assertIn(group, text)
        # No giant argparse choices blob, no boxed plus signs.
        self.assertNotIn("{create,project", text)
        self.assertNotIn("+--[", text)
        self.assertIn("self", text)

    def test_category_shows_its_commands(self):
        code, text = self._capture(["self"])
        self.assertEqual(code, 0)
        self.assertIn("wob self", text)
        self.assertIn("status", text)
        self.assertIn("repair", text)
        self.assertIn("incidents", text)
        # It is a category menu, not the health report.
        self.assertNotIn("Summary", text)

    def test_help_topics(self):
        code, text = self._capture(["help", "self", "status"])
        self.assertEqual(code, 0)
        self.assertIn("wob self status", text)
        self.assertIn("--deep", text)

    def test_unknown_help_topic(self):
        code, _ = self._capture(["help", "nonsense"])
        self.assertEqual(code, 1)


class TestClean(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="wobble_clean_")
        self.old_cwd = os.getcwd()
        os.chdir(self.test_dir)

    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _make_mess(self, deep=False):
        (Path(self.test_dir) / "build").mkdir()
        (Path(self.test_dir) / "build" / "out.txt").write_text("x")
        (Path(self.test_dir) / "dist").mkdir()
        (Path(self.test_dir) / "app.apk").write_text("apk")
        (Path(self.test_dir) / "keep.txt").write_text("keep")
        if deep:
            (Path(self.test_dir) / "node_modules").mkdir()
            (Path(self.test_dir) / "node_modules" / "pkg.js").write_text("js")

    def test_clean_removes_artifacts_only(self):
        self._make_mess(deep=True)
        f = io.StringIO()
        with redirect_stdout(f):
            code = main(["--json", "clean"])
        self.assertEqual(code, 0)
        data = json.loads(f.getvalue())
        self.assertGreaterEqual(data["removed"], 3)
        self.assertFalse((Path(self.test_dir) / "build").exists())
        self.assertFalse((Path(self.test_dir) / "app.apk").exists())
        # node_modules survives a normal clean
        self.assertTrue((Path(self.test_dir) / "node_modules").exists())
        self.assertTrue((Path(self.test_dir) / "keep.txt").exists())

    def test_clean_all_removes_dependencies(self):
        self._make_mess(deep=True)
        f = io.StringIO()
        with redirect_stdout(f):
            code = main(["--json", "clean", "--all", "--yes"])
        self.assertEqual(code, 0)
        self.assertFalse((Path(self.test_dir) / "node_modules").exists())
        self.assertTrue((Path(self.test_dir) / "keep.txt").exists())

    def test_clean_already_clean(self):
        f = io.StringIO()
        with redirect_stdout(f):
            code = main(["--json", "clean"])
        self.assertEqual(code, 0)
        data = json.loads(f.getvalue())
        self.assertEqual(data["removed"], 0)


if __name__ == "__main__":
    unittest.main()
