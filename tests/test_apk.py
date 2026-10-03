"""
Test APK discovery, zero-dependency zip inspection, and honest install handling.
"""

import unittest
import tempfile
import zipfile
import shutil
from pathlib import Path

from wobble.android.apk import find_apks, inspect_apk, install_apk


class TestAPK(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="wobble_apk_")
        self.test_path = Path(self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_mock_apk(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("AndroidManifest.xml", b"\x03\x00\x08\x00com.example.mockapp\x00")
            zf.writestr("classes.dex", b"dex\n035\x00mock_dex_bytes")
            zf.writestr("resources.arsc", b"mock_resources")
            zf.writestr("lib/arm64-v8a/libnative.so", b"mock_so")
            zf.writestr("META-INF/CERT.RSA", b"mock_signature")

    def test_apk_discovery(self):
        apk_debug_dir = self.test_path / "app" / "build" / "outputs" / "apk" / "debug"
        apk_file = apk_debug_dir / "app-debug.apk"
        self._create_mock_apk(apk_file)

        discovered = find_apks(self.test_path)
        self.assertEqual(len(discovered), 1)
        self.assertEqual(discovered[0].name, "app-debug.apk")

    def test_apk_inspection(self):
        apk_file = self.test_path / "sample.apk"
        self._create_mock_apk(apk_file)

        info = inspect_apk(apk_file)
        self.assertNotIn("error", info)
        self.assertEqual(info["file_name"], "sample.apk")
        self.assertIn("classes.dex", info["dex_files"])
        self.assertIn("arm64-v8a", info["native_abis"])
        self.assertTrue(info["has_resources"])
        self.assertIn("META-INF/CERT.RSA", info["signatures"])
        self.assertIsNotNone(info["sha256"])

    def test_install_nonexistent_apk(self):
        fake_path = self.test_path / "does_not_exist.apk"
        res = install_apk(fake_path)
        self.assertFalse(res["success"])
        self.assertIn("not found", res["error"])


if __name__ == "__main__":
    unittest.main()
