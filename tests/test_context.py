"""
Test dynamic context, architecture, storage, and Termux environment detection.
"""

import unittest
from wobble.core.context import (
    is_termux,
    get_prefix,
    get_home,
    get_architecture,
    get_storage_info,
    get_memory_info,
    get_lan_ip,
    get_full_environment_report
)


class TestContext(unittest.TestCase):
    def test_get_prefix(self):
        prefix = get_prefix()
        self.assertIsNotNone(prefix)
        self.assertTrue(str(prefix).startswith("/"))

    def test_get_home(self):
        home = get_home()
        self.assertIsNotNone(home)
        self.assertTrue(home.exists())

    def test_get_architecture(self):
        arch = get_architecture()
        self.assertIn(arch, ["aarch64", "arm", "x86_64", "x86", "unknown"])

    def test_get_storage_info(self):
        storage = get_storage_info()
        self.assertIn("free_bytes", storage)
        self.assertIn("free_human", storage)
        self.assertGreater(storage["total_bytes"], 0)

    def test_get_lan_ip(self):
        ip = get_lan_ip()
        self.assertIsInstance(ip, str)
        parts = ip.split(".")
        self.assertEqual(len(parts), 4)

    def test_full_report(self):
        report = get_full_environment_report()
        self.assertIn("termux", report)
        self.assertIn("platform", report)
        self.assertIn("storage", report)
        self.assertIn("network", report)


if __name__ == "__main__":
    unittest.main()
