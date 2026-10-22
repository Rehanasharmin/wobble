"""Test the ASCII theme, colour handling, and layout widths."""

import unittest

from wobble.core import theme


class TestBanner(unittest.TestCase):
    def test_banner_is_pure_ascii(self):
        for line in theme.BANNER_ART.splitlines():
            self.assertTrue(all(ord(ch) < 128 for ch in line), line)

    def test_banner_lines_are_aligned(self):
        widths = {len(line) for line in theme.BANNER_ART.splitlines()}
        self.assertEqual(len(widths), 1)

    def test_banner_respects_colour_flag(self):
        plain = theme.banner(False)
        colored = theme.banner(True)
        self.assertNotIn("\033[", plain)
        self.assertIn("\033[", colored)
        self.assertEqual(theme.strip_ansi(colored).splitlines()[:5],
                         plain.splitlines()[:5])


class TestLayout(unittest.TestCase):
    def test_rule_and_box_widths(self):
        for width in (40, 64, 68):
            self.assertEqual(len(theme.rule("title", width=width, use_color=False)), width)
            lines = theme.box("title", ["row", "x" * 200], width=width, use_color=False).splitlines()
            self.assertTrue(all(len(line) == width for line in lines), [len(l) for l in lines])

    def test_badge_and_progress_are_ascii(self):
        for status in ("ok", "warning", "missing", "error", "info"):
            badge = theme.badge(status, use_color=False)
            self.assertTrue(all(ord(ch) < 128 for ch in badge))
        bar = theme.progress_bar(42, width=10, use_color=False)
        self.assertIn("42%", bar)
        self.assertEqual(theme.visible_len(bar), len(bar))

    def test_kv_alignment(self):
        row = theme.kv("version", "1.2.0", use_color=False, width=10)
        self.assertTrue(row.startswith("version:  "))
        self.assertIn("1.2.0", row)


if __name__ == "__main__":
    unittest.main()
