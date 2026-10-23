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
    def test_headings_are_plain(self):
        # Section headings used to be ``+--[ title ]-----+`` banners. They are
        # now a single word, so the output stays quiet and copy-pasteable.
        self.assertEqual(theme.rule("title", use_color=False), "title")
        self.assertNotIn("+", theme.rule("title", use_color=False))
        self.assertNotIn("[", theme.rule("title", use_color=False))
        divider = theme.rule("", width=40, use_color=False)
        self.assertEqual(divider, "-" * 40)

    def test_box_has_no_border(self):
        lines = theme.box("title", ["row", "x" * 200], width=40, use_color=False).splitlines()
        self.assertEqual(lines[0], "title")
        self.assertEqual(lines[1], "  row")
        self.assertTrue(all(len(line) <= 40 for line in lines), lines)
        for line in lines:
            self.assertNotIn("|", line)
            self.assertNotIn("+", line)

    def test_badge_and_progress_are_ascii(self):
        for status in ("ok", "warning", "missing", "error", "info"):
            badge = theme.badge(status, use_color=False)
            self.assertTrue(all(ord(ch) < 128 for ch in badge), badge)
            self.assertNotIn("[", badge)
            self.assertEqual(len(badge), theme.BADGE_WIDTH)
        bar = theme.progress_bar(42, width=10, use_color=False)
        self.assertIn("42%", bar)
        self.assertEqual(theme.visible_len(bar), len(bar))

    def test_check_row_aligns_details(self):
        first = theme.check("ok", "a", "one", use_color=False, label_width=10)
        second = theme.check("warn", "bb", "two", use_color=False, label_width=10)
        self.assertEqual(first.index("one"), second.index("two"))

    def test_kv_alignment(self):
        row = theme.kv("version", "1.2.0", use_color=False, width=10)
        self.assertTrue(row.startswith("version:  "))
        self.assertIn("1.2.0", row)


class TestHealthMeter(unittest.TestCase):
    def test_invert_makes_high_scores_green(self):
        from wobble.core import theme

        healthy = theme.progress_bar(100, use_color=True, invert=True)
        unhealthy = theme.progress_bar(10, use_color=True, invert=True)
        self.assertIn(theme.GREEN, healthy)
        self.assertIn(theme.RED, unhealthy)

    def test_default_meter_still_treats_high_as_hot(self):
        from wobble.core import theme

        self.assertIn(theme.RED, theme.progress_bar(99, use_color=True))
        self.assertIn(theme.GREEN, theme.progress_bar(10, use_color=True))


if __name__ == "__main__":
    unittest.main()
