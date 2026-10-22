"""Security and performance checks for the zero-dependency preview server."""

import gzip
import os
import tempfile
import unittest
from pathlib import Path

from wobble.web.preview import _gzip_payload, _is_blocked


class TestPreviewBlocking(unittest.TestCase):
    def test_blocks_dotfiles_and_git(self):
        for path in ("/.env", "/.git/config", "/.wobble/projects.json",
                     "/.github/workflows/ci.yml"):
            self.assertTrue(_is_blocked(path), path)

    def test_blocks_traversal_and_encoded_traversal(self):
        for path in ("/../etc/passwd", "/%2e%2e/%2e%2e/etc/passwd",
                     "/..%2f..%2fetc/passwd", "/a/../../b"):
            self.assertTrue(_is_blocked(path), path)

    def test_blocks_secret_files(self):
        for path in ("/secrets.json", "/server.pem", "/release.jks",
                     "/debug.keystore", "/id_rsa", "/local.properties", "/app.log"):
            self.assertTrue(_is_blocked(path), path)

    def test_allows_normal_assets(self):
        for path in ("/", "/index.html", "/dist/assets/app.js",
                     "/css/style.css", "/images/logo.svg", "/api/data?x=1"):
            self.assertFalse(_is_blocked(path), path)


class TestGzipCache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="wobble_gzip_")
        self.path = Path(self.tmp) / "big.txt"
        self.path.write_text("wobble " * 2000)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_compresses_text(self):
        stat = os.stat(self.path)
        payload = _gzip_payload(self.path, stat)
        self.assertIsNotNone(payload)
        self.assertLess(len(payload), stat.st_size)
        self.assertEqual(gzip.decompress(payload), self.path.read_bytes())

    def test_cache_hit_returns_identical_bytes(self):
        stat = os.stat(self.path)
        first = _gzip_payload(self.path, stat)
        second = _gzip_payload(self.path, stat)
        self.assertIs(first, second)

    def test_does_not_expand_incompressible_data(self):
        binary = Path(self.tmp) / "noise.bin"
        binary.write_bytes(os.urandom(4096))
        stat = os.stat(binary)
        payload = _gzip_payload(binary, stat)
        # Random data does not compress; the helper must return None so the
        # server falls back to sending raw bytes.
        self.assertIsNone(payload)


if __name__ == "__main__":
    unittest.main()
