"""
Test doctor diagnostics and actionable recommendations.
"""

import unittest
from wobble.core.doctor import inspect_environment, run_doctor


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
        report = run_doctor(json_mode=True)
        self.assertIn("status", report)
        self.assertIn("counts", report)
        self.assertIn("checks", report)
        self.assertEqual(report["counts"]["ok"] + report["counts"]["warning"] + report["counts"]["missing"] + report["counts"]["error"], len(report["checks"]))


if __name__ == "__main__":
    unittest.main()
