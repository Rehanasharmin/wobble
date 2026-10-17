"""
Test crash-safe filesystem utilities and configuration corruption recovery.
"""

import json
import os
import unittest
import tempfile
import shutil
from pathlib import Path

from wobble.core.fsutil import atomic_write_text, atomic_write_json, backup_corrupted_file
from wobble.core.config import ConfigManager, DEFAULT_CONFIG


class TestFsUtil(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="wobble_fsutil_")
        self.test_path = Path(self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_atomic_write_text(self):
        target = self.test_path / "notes.txt"
        atomic_write_text(target, "hello wobble")
        self.assertEqual(target.read_text(encoding="utf-8"), "hello wobble")
        # No stray temp files left behind
        leftovers = [p for p in self.test_path.iterdir() if p.name != "notes.txt"]
        self.assertEqual(leftovers, [])

    def test_atomic_write_json_roundtrip(self):
        target = self.test_path / "nested" / "data.json"
        payload = {"name": "wobble", "count": 3, "items": ["a", "b"]}
        atomic_write_json(target, payload)
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), payload)

    def test_atomic_overwrite_keeps_valid_json(self):
        target = self.test_path / "data.json"
        atomic_write_json(target, {"v": 1})
        atomic_write_json(target, {"v": 2})
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"v": 2})

    def test_backup_corrupted_file(self):
        target = self.test_path / "config.json"
        target.write_text("{corrupt", encoding="utf-8")
        backup = backup_corrupted_file(target)
        self.assertTrue(backup.exists())
        self.assertFalse(target.exists())
        self.assertEqual(backup.read_text(encoding="utf-8"), "{corrupt")


class TestConfigRecovery(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="wobble_cfg_")
        self.test_path = Path(self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_corrupt_config_backed_up_and_reset(self):
        cfg_path = self.test_path / "config.json"
        cfg_path.write_text("not-json{{", encoding="utf-8")

        manager = ConfigManager(config_path=cfg_path)
        # Falls back to defaults
        self.assertEqual(manager.get("default_web_framework"), DEFAULT_CONFIG["default_web_framework"])
        # Corrupted file preserved for manual recovery
        backup = cfg_path.with_name("config.json.corrupt.bak")
        self.assertTrue(backup.exists())
        self.assertEqual(backup.read_text(encoding="utf-8"), "not-json{{")
        # Fresh valid config written in its place
        self.assertTrue(cfg_path.exists())
        self.assertIsInstance(json.loads(cfg_path.read_text(encoding="utf-8")), dict)

    def test_valid_config_merges_with_defaults(self):
        cfg_path = self.test_path / "config.json"
        cfg_path.write_text(json.dumps({"dev_server_port": 4321}), encoding="utf-8")
        manager = ConfigManager(config_path=cfg_path)
        self.assertEqual(manager.get("dev_server_port"), 4321)
        self.assertIn("default_author", manager.all())

    def test_set_persists_atomically(self):
        cfg_path = self.test_path / "config.json"
        manager = ConfigManager(config_path=cfg_path)
        manager.set("dev_server_port", "8080")
        reloaded = json.loads(cfg_path.read_text(encoding="utf-8"))
        self.assertEqual(reloaded["dev_server_port"], 8080)

    def test_non_object_config_recovers(self):
        cfg_path = self.test_path / "config.json"
        cfg_path.write_text("[1, 2, 3]", encoding="utf-8")
        manager = ConfigManager(config_path=cfg_path)
        self.assertEqual(manager.get("default_web_framework"), DEFAULT_CONFIG["default_web_framework"])


if __name__ == "__main__":
    unittest.main()
