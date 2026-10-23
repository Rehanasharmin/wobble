"""Health ledger, snapshot diffing, and probe-cache behaviour."""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from wobble.core import health, probecache


class LedgerTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="wobble_health_"))
        self._old_home = os.environ.get("HOME")
        os.environ["HOME"] = str(self.tmp)
        self._old_ttl = os.environ.get("WOBBLE_PROBE_TTL")
        os.environ["WOBBLE_PROBE_TTL"] = "3600"
        probecache.reset_for_tests()

    def tearDown(self):
        if self._old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self._old_home
        if self._old_ttl is None:
            os.environ.pop("WOBBLE_PROBE_TTL", None)
        else:
            os.environ["WOBBLE_PROBE_TTL"] = self._old_ttl
        probecache.reset_for_tests()
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestIncidentLedger(LedgerTestBase):
    def test_record_and_read(self):
        self.assertTrue(health.record_incident("crash", "TypeError: boom"))
        incidents = health.read_incidents()
        self.assertEqual(len(incidents), 1)
        self.assertEqual(incidents[0]["kind"], "crash")
        self.assertEqual(incidents[0]["message"], "TypeError: boom")
        self.assertEqual(incidents[0]["count"], 1)
        self.assertTrue((self.tmp / ".wobble" / "health" / "incidents.json").is_file())

    def test_duplicate_incidents_merge_into_a_counter(self):
        health.record_incident("crash", "Killed")
        health.record_incident("crash", "Killed")
        incidents = health.read_incidents()
        self.assertEqual(len(incidents), 1)
        self.assertEqual(incidents[0]["count"], 2)
        self.assertEqual(health.incident_summary()["repeat_count"], 2)

    def test_messages_are_sanitized_and_truncated(self):
        long_message = "x" * 900
        health.record_incident("crash", long_message)
        message = health.read_incidents()[0]["message"]
        self.assertLessEqual(len(message), health.MAX_MESSAGE)
        self.assertTrue(message.endswith("..."))

    def test_home_path_is_redacted(self):
        health.record_incident("crash", f"cannot open {self.tmp}/projects/demo")
        message = health.read_incidents()[0]["message"]
        self.assertNotIn(str(self.tmp), message)
        self.assertIn("~/projects/demo", message)

    def test_summary_orders_newest_first(self):
        health.record_incident("first", "one")
        path = health.incidents_path()
        data = json.loads(path.read_text())
        data["incidents"][0]["last_seen"] = 1.0
        path.write_text(json.dumps(data))
        health.record_incident("second", "two")
        summary = health.incident_summary()
        self.assertEqual(summary["last"]["kind"], "second")
        self.assertEqual(summary["total"], 2)

    def test_clear(self):
        health.record_incident("crash", "one")
        self.assertEqual(health.clear_incidents(), 1)
        self.assertEqual(health.read_incidents(), [])
        self.assertEqual(health.clear_incidents(), 0)

    def test_corrupt_ledger_never_raises(self):
        path = health.incidents_path()
        path.parent.mkdir(parents=True)
        path.write_text("{not json")
        self.assertEqual(health.read_incidents(), [])
        self.assertEqual(health.incident_summary()["total"], 0)
        self.assertTrue(health.record_incident("crash", "after corruption"))
        self.assertEqual(len(health.read_incidents()), 1)


class TestSnapshots(LedgerTestBase):
    def _check(self, name, status):
        return {"name": name, "status": status}

    def test_compare_detects_regressions_and_recoveries(self):
        previous = {"checks": {"Git": {"status": "ok", "since": 100},
                               "Java": {"status": "missing", "since": 100}}}
        current = {"checks": {"Git": {"status": "missing", "since": 200},
                              "Java": {"status": "ok", "since": 200}}}
        diff = health.compare_snapshots(previous, current, previous_at=100, now=200)
        self.assertEqual([r["name"] for r in diff["regressions"]], ["Git"])
        self.assertEqual([r["name"] for r in diff["recovered"]], ["Java"])
        self.assertEqual(diff["regressions"][0]["to"], "missing")

    def test_compare_tracks_new_removed_and_persistent(self):
        day = 86400
        previous = {"checks": {"Old": {"status": "ok", "since": 0},
                               "Stuck": {"status": "warning", "since": 0}}}
        current = {"checks": {"Stuck": {"status": "warning", "since": 0},
                              "New": {"status": "missing", "since": 5 * day}}}
        diff = health.compare_snapshots(previous, current, now=5 * day + 1)
        self.assertEqual([c["name"] for c in diff["new"]], ["New"])
        self.assertEqual([c["name"] for c in diff["removed"]], ["Old"])
        self.assertEqual([c["name"] for c in diff["persistent"]], ["Stuck"])
        self.assertEqual(diff["persistent"][0]["days"], 5)

    def test_save_and_diff_update_preserves_since(self):
        path = self.tmp / "baseline.json"
        first = [self._check("Git", "ok"), self._check("Java", "missing")]
        diff = health.diff_and_update(first, path=path)
        self.assertEqual(diff["regressions"], [])  # first baseline has nothing to compare
        since = json.loads(path.read_text())["checks"]["Java"]["since"]
        self.assertTrue(since)

        second = [self._check("Git", "missing"), self._check("Java", "missing")]
        diff = health.diff_and_update(second, path=path)
        self.assertEqual([r["name"] for r in diff["regressions"]], ["Git"])
        stored = json.loads(path.read_text())["checks"]
        self.assertEqual(stored["Java"]["since"], since)  # unchanged status keeps history
        self.assertGreater(stored["Git"]["since"], since)

    def test_no_save_leaves_baseline_untouched(self):
        path = self.tmp / "baseline.json"
        health.diff_and_update([self._check("Git", "ok")], path=path, save=True)
        before = path.read_text()
        diff = health.diff_and_update([self._check("Git", "missing")], path=path, save=False)
        self.assertEqual([r["name"] for r in diff["regressions"]], ["Git"])
        self.assertEqual(path.read_text(), before)


class TestProbeCache(LedgerTestBase):
    def test_put_get_round_trip_with_fingerprint(self):
        probecache.put("key", [True, "v1"], [1, 2, 3, 4])
        self.assertTrue(probecache.flush())
        probecache.reset_for_tests()
        hit, value = probecache.get("key", [1, 2, 3, 4])
        self.assertTrue(hit)
        self.assertEqual(value, [True, "v1"])

    def test_fingerprint_mismatch_invalidates(self):
        probecache.put("key", [True, "v1"], [1, 2, 3, 4])
        probecache.flush()
        probecache.reset_for_tests()
        self.assertFalse(probecache.get("key", [9, 9, 9, 9])[0])

    def test_expired_entries_are_ignored(self):
        probecache.put("key", [True, "v1"], [1])
        probecache.flush()
        probecache.reset_for_tests()
        self.assertFalse(probecache.get("key", [1], ttl=0)[0])
        self.assertTrue(probecache.get("key", [1], ttl=3600)[0])

    def test_ttl_zero_disables_storage(self):
        old = os.environ.get("WOBBLE_PROBE_TTL")
        os.environ["WOBBLE_PROBE_TTL"] = "0"
        try:
            self.assertFalse(probecache.enabled())
            probecache.put("key", [True, "v1"], [1])
            self.assertFalse(probecache.flush())
            self.assertFalse(probecache.get("key", [1])[0])
        finally:
            os.environ["WOBBLE_PROBE_TTL"] = old or "3600"

    def test_clear_removes_entries(self):
        probecache.put("key", [True, "v1"], [1])
        probecache.flush()
        self.assertEqual(probecache.clear(), 1)
        self.assertEqual(probecache.stats()["entries"], 0)


if __name__ == "__main__":
    unittest.main()
