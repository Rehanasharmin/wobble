"""Verify install advice against upstream Termux package names.

The doctor's copy-paste commands are the interface between Wobble and the
package repositories.  These tests pin the names that were checked against
``termux/termux-packages`` (see ``docs/termux_packages.md``) and make sure the
advice is resolved for the host instead of always printing ``pkg install``.
"""

import io
import unittest
from contextlib import redirect_stdout
from unittest import mock

from wobble.core import doctor, packages

#: Names verified in the official repository on 2026-10-23.
VERIFIED_TERMUX_PACKAGES = {
    "git", "python", "nodejs", "php",
    "openjdk-17", "openjdk-21", "openjdk-25",
    "gradle", "aapt", "aapt2", "apksigner",
    "android-tools", "termux-tools", "zip", "unzip",
}


class TestPackageMap(unittest.TestCase):
    def test_termux_names_are_verified(self):
        for key, families in packages.PACKAGE_MAP.items():
            for name in families.get(packages.TERMUX, ()):
                self.assertIn(name, VERIFIED_TERMUX_PACKAGES,
                              f"{key} maps to unverified Termux package {name}")

    def test_no_removed_jdk_is_ever_suggested(self):
        termux_names = {name for families in packages.PACKAGE_MAP.values()
                        for name in families.get(packages.TERMUX, ())}
        self.assertNotIn("openjdk-11", termux_names)
        self.assertNotIn("openjdk17", termux_names)
        self.assertNotIn("android-sdk", termux_names)

    def test_termux_toolchain_command(self):
        keys = ["jdk", "gradle", "aapt", "aapt2", "apksigner", "zip"]
        self.assertEqual(
            packages.install_command(keys, packages.TERMUX),
            "pkg install -y openjdk-17 gradle aapt aapt2 apksigner zip unzip",
        )
        self.assertEqual(packages.unsupported_keys(keys, packages.TERMUX), [])

    def test_aapt2_is_its_own_package(self):
        # `aapt` ships aapt + zipalign; aapt2 is a split package, so the doctor
        # hint must request both.
        self.assertEqual(packages.packages_for(["aapt"], packages.TERMUX), ["aapt"])
        self.assertEqual(packages.packages_for(["aapt2"], packages.TERMUX), ["aapt2"])

    def test_debian_uses_distribution_names(self):
        self.assertEqual(
            packages.install_command(["jdk"], packages.APT),
            "sudo apt install -y openjdk-17-jdk",
        )
        self.assertEqual(
            packages.install_command(["python"], packages.APT),
            "sudo apt install -y python3 python3-pip",
        )
        self.assertEqual(packages.unsupported_keys(["aapt", "apksigner"], packages.APT),
                         ["aapt", "apksigner"])

    def test_unavailable_tools_point_at_sdkmanager(self):
        hint = packages.install_hint(["aapt", "aapt2", "apksigner"])
        if packages.package_family() == packages.TERMUX:
            self.assertIn("pkg install -y aapt aapt2 apksigner", hint)
        else:
            self.assertIn("sdkmanager", hint)

    def test_update_command_known_for_each_family(self):
        for family in (packages.TERMUX, packages.APT, packages.DNF, packages.PACMAN):
            self.assertTrue(packages.update_command(family))


class TestQuickFix(unittest.TestCase):
    def _results(self, names, status="missing"):
        return [doctor.CheckResult(name=name, category="Android Toolchain", status=status)
                for name in names]

    def test_termux_quick_fix_installs_aapt2_and_skips_optional_php(self):
        results = self._results(["Java / JDK", "Android Build Tools", "PHP"])
        with mock.patch.object(packages, "package_family", return_value=packages.TERMUX):
            fix = doctor.build_quick_fix(results)
        self.assertEqual(
            fix["command"],
            "pkg install -y openjdk-17 aapt aapt2 apksigner",
        )
        self.assertNotIn("php", fix["command"])
        self.assertIn("pkg update", fix["note"])

    def test_non_termux_quick_fix_never_prints_pkg(self):
        results = self._results(["Java / JDK", "Gradle"])
        with mock.patch.object(packages, "package_family", return_value=packages.APT):
            fix = doctor.build_quick_fix(results)
        self.assertNotIn("pkg", fix["command"])
        self.assertTrue(fix["command"].startswith("sudo apt install -y"))
        self.assertIn("openjdk-17-jdk", fix["command"])

    def test_quick_fix_is_ignored_when_everything_passes(self):
        results = self._results(["Git", "Python"], status="ok")
        with mock.patch.object(packages, "package_family", return_value=packages.TERMUX):
            fix = doctor.build_quick_fix(results)
        self.assertIsNone(fix["command"])


class TestDoctorReportIncludesQuickFix(unittest.TestCase):
    def test_json_report_has_resolved_quick_fix(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            report = doctor.run_doctor(json_mode=True, quick=True, save=False)
        self.assertIn("quick_fix", report)
        self.assertIn("package_manager", report["quick_fix"])
        self.assertIn("unavailable", report["quick_fix"])


if __name__ == "__main__":
    unittest.main()
