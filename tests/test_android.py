"""
Test Android plugin, limitations reporter, and SDK detection.
"""

import unittest
from pathlib import Path

from wobble.android.limitations import get_android_limitations_report
from wobble.android.sdk import get_sdk_status
from wobble.plugins.loader import get_plugin
from wobble.core.context import get_android_sdk_candidates, get_java_home_candidates


class TestAndroid(unittest.TestCase):
    def test_android_limitations_report(self):
        report = get_android_limitations_report()
        self.assertIn("title", report)
        self.assertIn("principles", report)
        self.assertIn("limitations", report)

        topics = [lim["topic"] for lim in report["limitations"]]
        self.assertIn("APK Installation on Device", topics)
        self.assertIn("W^X (Write XOR Execute) & execve Constraints", topics)
        self.assertIn("Phantom Process Killer & RAM Constraints", topics)

    def test_android_sdk_status(self):
        status = get_sdk_status()
        self.assertIn("found", status)
        self.assertIn("platforms", status)
        self.assertIn("build_tools", status)

    def test_android_plugin_build_command(self):
        p = get_plugin("android")
        self.assertIsNotNone(p)

        cmd_debug = p.get_build_command(Path("/tmp"), {"release": False})
        self.assertIn("assembleDebug", cmd_debug)
        self.assertIn("--no-daemon", cmd_debug)

        cmd_release = p.get_build_command(Path("/tmp"), {"release": True})
        self.assertIn("assembleRelease", cmd_release)
        self.assertIn("--no-daemon", cmd_release)


if __name__ == "__main__":
    unittest.main()
