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


class TestAndroidPropertyParsing(unittest.TestCase):
    def test_parse_getprop_output(self):
        from wobble.core.context import parse_getprop_output

        output = "\n".join([
            "[ro.build.version.release]: [15]",
            "[ro.build.version.sdk]: [35]",
            "[ro.product.model]: [Pixel 8 Pro]",
            "malformed line",
            "[empty]: []",
        ])
        props = parse_getprop_output(output)
        self.assertEqual(props["ro.build.version.release"], "15")
        self.assertEqual(props["ro.build.version.sdk"], "35")
        # Values may contain spaces; they must survive intact.
        self.assertEqual(props["ro.product.model"], "Pixel 8 Pro")
        self.assertNotIn("empty", props)
        self.assertNotIn("malformed line", props)

    def test_parse_getprop_handles_empty_input(self):
        from wobble.core.context import parse_getprop_output

        self.assertEqual(parse_getprop_output(""), {})
        self.assertEqual(parse_getprop_output(None), {})


class TestMountInfo(unittest.TestCase):
    def test_mount_info_for_existing_path(self):
        from pathlib import Path
        from wobble.core.context import get_mount_info

        info = get_mount_info(str(Path.home()))
        self.assertIn("mountpoint", info)
        self.assertIn("options", info)
        self.assertTrue(info["mountpoint"].startswith("/"))
