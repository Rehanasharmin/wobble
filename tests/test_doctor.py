"""
Test doctor diagnostics and actionable recommendations.
"""

import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout

from wobble.core import doctor, health, probecache
from wobble.core.doctor import (
    check_tools_parallel,
    doctor_exit_code,
    inspect_environment,
    resolve_categories,
    run_doctor,
)


class TestDoctor(unittest.TestCase):
    def test_inspect_environment(self):
        results = inspect_environment()
        self.assertGreater(len(results), 5)

        categories = set()
        for r in results:
            self.assertIn(r.status, ["ok", "warning", "missing", "error"])
            self.assertTrue(len(r.name) > 0)
            categories.add(r.category)
            if r.status in ("missing", "warning"):
                # Ensure problems have actionable explanations or fixes
                self.assertTrue(r.problem is not None or r.details is not None)

        self.assertIn("System", categories)
        self.assertIn("Dev Tools", categories)

    def test_run_doctor_data(self):
        f = io.StringIO()
        with redirect_stdout(f):
            report = run_doctor(json_mode=True)
        self.assertIn("status", report)
        self.assertIn("counts", report)
        self.assertIn("checks", report)
        self.assertEqual(
            report["counts"]["ok"] + report["counts"]["warning"]
            + report["counts"]["missing"] + report["counts"]["error"],
            len(report["checks"]),
        )

    def test_report_includes_cache_timings_and_history(self):
        f = io.StringIO()
        with redirect_stdout(f):
            report = run_doctor(json_mode=True, timings=True)
        self.assertIn("cache", report)
        self.assertIn("timings", report)
        self.assertIn("regressions", report)
        self.assertIn("recovered", report)
        self.assertIn("persistent", report)
        self.assertIn("elapsed_ms", report)
        self.assertGreaterEqual(report["elapsed_ms"], 0)
        json.dumps(report)

    def test_wobble_runtime_category_is_included(self):
        report = run_doctor(json_mode=True)
        categories = {check["category"] for check in report["checks"]}
        self.assertIn("Wobble Runtime", categories)

    def test_quick_mode_skips_probe_subprocesses(self):
        results = inspect_environment(quick=True)
        statuses = {result.status for result in results}
        self.assertTrue(statuses.issubset({"ok", "warning", "missing", "error"}))
        self.assertTrue(inspect_environment.last_timings["quick"])


class TestDoctorFiltering(unittest.TestCase):
    def test_resolve_categories_aliases(self):
        self.assertEqual(resolve_categories("system"), ["System"])
        self.assertEqual(resolve_categories("tools,web"), ["Dev Tools", "Web Tools"])
        self.assertEqual(resolve_categories("android,sdk"), ["Android Toolchain"])
        self.assertIsNone(resolve_categories(None))
        self.assertIsNone(resolve_categories("  "))

    def test_unknown_category_is_rejected(self):
        with self.assertRaises(ValueError):
            resolve_categories("nope")

    def test_only_filters_results(self):
        results = inspect_environment(only="resources")
        self.assertTrue(results)
        self.assertEqual({result.category for result in results}, {"Resources"})

    def test_filtered_run_skips_baseline(self):
        report = run_doctor(json_mode=True, only="system")
        self.assertEqual(report["baseline"], "skipped (filtered run)")
        self.assertEqual(report["regressions"], [])


class TestExitCodes(unittest.TestCase):
    def _report(self, *statuses):
        return {"checks": [{"name": f"c{i}", "status": s} for i, s in enumerate(statuses)]}

    def test_thresholds(self):
        self.assertEqual(doctor_exit_code(self._report("ok", "ok"), "never"), 0)
        self.assertEqual(doctor_exit_code(self._report("ok", "warning"), "never"), 0)
        self.assertEqual(doctor_exit_code(self._report("ok", "warning"), "warning"), 1)
        self.assertEqual(doctor_exit_code(self._report("ok", "warning"), "missing"), 0)
        self.assertEqual(doctor_exit_code(self._report("missing"), "missing"), 1)
        self.assertEqual(doctor_exit_code(self._report("missing"), "error"), 0)
        self.assertEqual(doctor_exit_code(self._report("error"), "error"), 1)

    def test_strict_cli_exit(self):
        import subprocess
        import sys
        from pathlib import Path
        repo = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "-m", "wobble", "doctor", "--json", "--strict",
             "--only", "resources", "--no-save"],
            cwd=str(repo), capture_output=True, text=True, timeout=90,
        )
        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, payload["exit_code"])
        self.assertIn(result.returncode, (0, 1))


class TestProbeCacheWarmStart(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="wobble_doctor_")
        self._old_home = os.environ.get("HOME")
        self._old_no_cache = os.environ.get("WOBBLE_NO_CACHE")
        os.environ["HOME"] = self.tmp
        os.environ.pop("WOBBLE_NO_CACHE", None)
        probecache.reset_for_tests()

    def tearDown(self):
        if self._old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self._old_home
        if self._old_no_cache is None:
            os.environ.pop("WOBBLE_NO_CACHE", None)
        else:
            os.environ["WOBBLE_NO_CACHE"] = self._old_no_cache
        probecache.reset_for_tests()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_second_probe_run_hits_cache(self):
        checks = {"git": ("/usr/bin/git", "--version")}
        if not os.path.exists(checks["git"][0]):
            self.skipTest("git is not installed")
        first = check_tools_parallel(dict(checks), refresh=True)
        self.assertFalse(check_tools_parallel.last_sources.get("git"))
        self.assertTrue(probecache.flush())
        probecache.reset_for_tests()

        second = check_tools_parallel(dict(checks))
        self.assertEqual(first["git"][0], second["git"][0])
        self.assertTrue(check_tools_parallel.last_sources.get("git"))
        self.assertGreater(probecache.stats()["entries"], 0)

    def test_no_cache_environment_disables_reads(self):
        os.environ["WOBBLE_NO_CACHE"] = "1"
        self.assertFalse(probecache.enabled())
        hit, _value = probecache.get("anything", [1])
        self.assertFalse(hit)


if __name__ == "__main__":
    unittest.main()
