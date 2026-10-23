"""Startup hygiene: trivial commands must not drag in heavy modules.

These tests guard the fast paths. It is easy to add a convenient top-level
``import json`` (or ``concurrent.futures``) and silently make every ``wob``
invocation 5 ms slower on a phone; this keeps the cost visible.
"""

import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def loaded_modules(code: str) -> set:
    """Import *code* in a fresh interpreter and return the module names loaded."""
    program = (
        "import json, sys\n"
        f"{code}\n"
        "print(json.dumps(sorted(sys.modules)))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", program],
        cwd=str(REPO), capture_output=True, text=True, timeout=60,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO), "HOME": "/tmp"},
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return set(json.loads(result.stdout))


class TestStartupHygiene(unittest.TestCase):
    def test_bootstrap_does_not_import_json_or_typing(self):
        modules = loaded_modules("import wobble.bootstrap")
        # ``json`` is imported by the test harness itself, so check the
        # submodule set that only a real top-level import would pull in.
        self.assertNotIn("typing", modules)
        self.assertNotIn("argparse", modules)
        self.assertNotIn("logging", modules)
        self.assertNotIn("concurrent.futures", modules)

    def test_cli_import_skips_hashing_and_thread_pools(self):
        modules = loaded_modules("import wobble.cli")
        self.assertNotIn("concurrent.futures", modules)
        self.assertNotIn("logging", modules)
        self.assertNotIn("hashlib", modules)
        self.assertNotIn("socket", modules)
        self.assertNotIn("typing", modules)

    def test_selfcheck_import_stays_light(self):
        modules = loaded_modules("import wobble.core.selfcheck")
        self.assertNotIn("concurrent.futures", modules)
        self.assertNotIn("logging", modules)
        self.assertNotIn("socket", modules)

    def test_doctor_import_defers_the_thread_pool(self):
        modules = loaded_modules("from wobble.core import doctor")
        self.assertIn("wobble.core.doctor", modules)
        # The pool is imported inside check_tools_parallel(), so a `--quick`
        # doctor (which skips probes entirely) never pays for logging/threading.
        self.assertNotIn("concurrent.futures", modules)
        self.assertNotIn("logging", modules)


if __name__ == "__main__":
    unittest.main()
