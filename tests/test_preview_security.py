"""Security and performance checks for the zero-dependency preview server."""

import gzip
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from wobble.web.preview import (
    _GZIP_MAX_INPUT_BYTES, _accepted, _gzip_payload, _is_blocked,
    _open_contained_file,
)


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


class TestAcceptEncoding(unittest.TestCase):
    class Headers(dict):
        def get(self, key, default=""):
            return super().get(key, default)

    def test_honors_quality_values(self):
        for value, expected in (("gzip", True), ("br, gzip;q=0.7", True),
                                ("gzip;q=0", False), ("gzip;q=0.000", False),
                                ("gzip;q=bogus", False), ("*;q=0.5", True),
                                ("*;q=0, gzip;q=1", True), ("br", False)):
            with self.subTest(value=value):
                self.assertEqual(_accepted(self.Headers({"Accept-Encoding": value}), "gzip"), expected)


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

    def test_skips_large_files_before_reading_them(self):
        large = Path(self.tmp) / "large.txt"
        large.write_bytes(b"x" * (_GZIP_MAX_INPUT_BYTES + 1))
        with patch("wobble.web.preview.open", side_effect=AssertionError("must not read"), create=True):
            self.assertIsNone(_gzip_payload(large, os.stat(large)))

    def test_compresses_from_already_open_descriptor_without_reopening_path(self):
        stat = os.stat(self.path)
        with self.path.open("rb") as source:
            with patch("builtins.open", side_effect=AssertionError("path must not be reopened")):
                payload = _gzip_payload(self.path, stat, source=source)
            self.assertEqual(gzip.decompress(payload), self.path.read_bytes())
            self.assertEqual(source.read(7), b"wobble ")

    def test_cache_invalidates_replaced_file_with_preserved_mtime_and_size(self):
        original_stat = self.path.stat()
        original = _gzip_payload(self.path, original_stat)
        replacement = self.path.with_suffix(".replacement")
        replacement.write_text("different " * 1400)
        self.assertEqual(replacement.stat().st_size, original_stat.st_size)
        os.utime(replacement, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        os.replace(replacement, self.path)

        updated = _gzip_payload(self.path, self.path.stat())
        self.assertIsNotNone(updated)
        self.assertNotEqual(updated, original)
        self.assertEqual(gzip.decompress(updated), self.path.read_bytes())


class TestContainedOpen(unittest.TestCase):
    def test_opens_only_regular_files_beneath_pinned_root(self):
        with (tempfile.TemporaryDirectory(prefix="wobble_root_") as root_dir,
              tempfile.TemporaryDirectory(prefix="wobble_outside_") as outside_dir):
            root = Path(root_dir).resolve()
            safe = root / "safe.txt"
            safe.write_text("inside")
            outside = Path(outside_dir) / "secret.txt"
            outside.write_text("outside")
            (root / "escape.txt").symlink_to(outside)
            root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                with _open_contained_file(root_fd, root, safe) as handle:
                    self.assertEqual(handle.read(), b"inside")
                self.assertIsNone(_open_contained_file(root_fd, root, root / "escape.txt"))
                self.assertIsNone(_open_contained_file(root_fd, root, outside))
            finally:
                os.close(root_fd)


if __name__ == "__main__":
    unittest.main()
