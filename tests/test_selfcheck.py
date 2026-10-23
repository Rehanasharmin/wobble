"""Self-check engine: healthy installs, breakage detection, repair, CLI wiring."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from wobble import __version__
from wobble.core import health, installer, probecache, selfcheck

REPO = Path(__file__).resolve().parents[1]


class SelfCheckBase(unittest.TestCase):
    """Install Wobble into a throwaway prefix for every test."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="wobble_selfcheck_"))
        self.home = self.tmp / "home"
        self.root = self.tmp / "root"
        self.bin_dir = self.tmp / "bin"
        self.home.mkdir(parents=True)
        self._env_backup = {key: os.environ.get(key) for key in
                            ("HOME", "WOBBLE_INSTALL_DIR", "WOBBLE_BIN_DIR", "PATH",
                             "WOBBLE_NO_CACHE")}
        os.environ["HOME"] = str(self.home)
        os.environ["WOBBLE_INSTALL_DIR"] = str(self.root)
        os.environ["WOBBLE_BIN_DIR"] = str(self.bin_dir)
        os.environ["PATH"] = f"{self.bin_dir}:{os.environ.get('PATH', '')}"
        probecache.reset_for_tests()
        self.data = installer.install(
            source_root=REPO,
            install_root=self.root,
            bin_dir=self.bin_dir,
            completions=True,
            update_path=False,
        )
        self.app_dir = self.root / "app"

    def tearDown(self):
        for key, value in self._env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        probecache.reset_for_tests()
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- helpers --------------------------------------------------------
    def inspect(self, **kwargs):
        return selfcheck.inspect(install_root=self.root, bin_dir=self.bin_dir, **kwargs)

    def codes(self, report, status=None):
        return {c["code"] for c in report["checks"]
                if status is None or c["status"] == status}

    def issue_codes(self, report):
        return {c["code"] for c in report["issues"]}

    def run_cli(self, *args):
        """Run the CLI from the test tree.

        ``python -m wobble`` is used rather than the installed launcher so a
        test can delete the launcher and still invoke the repair command; the
        installed launcher itself is covered by tests/test_installer.py.
        """
        import sys

        env = dict(os.environ)
        env["HOME"] = str(self.home)
        env["WOBBLE_INSTALL_DIR"] = str(self.root)
        env["WOBBLE_BIN_DIR"] = str(self.bin_dir)
        env["PATH"] = f"{self.bin_dir}:{env.get('PATH', '')}"
        env["PYTHONPATH"] = str(REPO)
        return subprocess.run(
            [sys.executable, "-m", "wobble", *args],
            env=env, capture_output=True, text=True, timeout=60, cwd=str(REPO),
        )


class TestHealthyInstall(SelfCheckBase):
    def test_reports_standalone_install(self):
        report = self.inspect()
        self.assertEqual(report["mode"], "standalone")
        self.assertEqual(report["version"], __version__)
        self.assertEqual(report["file_count"], self.data["file_count"])
        self.assertGreater(report["file_count"], 20)
        self.assertIn(report["status"], ("healthy", "degraded"))
        self.assertEqual(report["counts"]["critical"], 0)
        self.assertTrue(report["ok"])
        self.assertGreaterEqual(report["score"], 80)

    def test_all_expected_checks_are_present(self):
        codes = self.codes(self.inspect())
        for code in ("python.interpreter", "install.manifest", "install.version",
                     "runtime.files", "runtime.bytecode", "launcher.present",
                     "launcher.path", "environment.path", "shell.completions",
                     "data.writable", "data.config", "disk.space",
                     "environment.storage", "installer.leftovers", "history.incidents"):
            self.assertIn(code, codes)
        self.assertNotIn("integrity.hashes", codes)  # fast mode does not hash

    def test_report_is_json_serializable(self):
        report = self.inspect(deep=True)
        json.dumps(report)
        self.assertIn("integrity.hashes", self.codes(report))
        self.assertIn("runtime.imports", self.codes(report))

    def test_deep_mode_verifies_hashes_and_imports(self):
        report = self.inspect(deep=True)
        hashes = next(c for c in report["checks"] if c["code"] == "integrity.hashes")
        self.assertEqual(hashes["status"], "ok")
        self.assertEqual(hashes["data"]["checked"], report["file_count"])
        imports = next(c for c in report["checks"] if c["code"] == "runtime.imports")
        self.assertEqual(imports["status"], "ok")

    def test_source_checkout_still_reports_incidents(self):
        health.record_incident("crash", "ValueError: in a checkout")
        report = selfcheck.inspect(install_root=self.tmp / "none",
                                   bin_dir=self.tmp / "none-bin")
        finding = next(c for c in report["checks"] if c["code"] == "history.incidents")
        self.assertEqual(finding["status"], "warning")
        self.assertIn("ValueError: in a checkout", finding["detail"])
        self.assertEqual(selfcheck.exit_code(report), 0)
        self.assertEqual(selfcheck.exit_code(report, strict=True), 1)
        self.assertEqual(report["status"], "degraded")

    def test_source_checkout_reports_info_not_failure(self):
        report = selfcheck.inspect(install_root=self.tmp / "missing-root",
                                   bin_dir=self.tmp / "missing-bin")
        self.assertEqual(report["mode"], "source-checkout")
        self.assertEqual(report["status"], "healthy")
        self.assertEqual(selfcheck.exit_code(report), 0)

    def test_render_contains_summary(self):
        rendered = selfcheck.render(self.inspect(), use_color=False)
        self.assertIn("wobble self status", rendered)
        self.assertIn("summary", rendered.lower())
        self.assertIn("ms", rendered)
        # The new layout is deliberately quiet: no boxed rules, no badges.
        self.assertNotIn("+--[", rendered)
        self.assertNotIn("[ OK ]", rendered)


class TestBreakageDetection(SelfCheckBase):
    def test_missing_file_is_critical(self):
        (self.app_dir / "wobble" / "core" / "theme.py").unlink()
        report = self.inspect()
        self.assertEqual(report["status"], "broken")
        self.assertIn("runtime.files", self.issue_codes(report))
        self.assertEqual(selfcheck.exit_code(report), 1)
        self.assertEqual(selfcheck.exit_code(report, strict=True), 1)

    def test_resized_file_is_a_warning_until_hashed(self):
        target = self.app_dir / "wobble" / "core" / "theme.py"
        target.write_text(target.read_text() + "\n# tampered\n")
        report = self.inspect()
        finding = next(c for c in report["checks"] if c["code"] == "runtime.files")
        self.assertEqual(finding["status"], "warning")
        self.assertEqual(report["status"], "degraded")
        self.assertEqual(selfcheck.exit_code(report), 0)
        self.assertEqual(selfcheck.exit_code(report, strict=True), 1)

        deep = self.inspect(deep=True)
        self.assertIn("integrity.hashes", self.issue_codes(deep))
        self.assertIn("wobble/core/theme.py",
                      next(c for c in deep["checks"] if c["code"] == "integrity.hashes")["data"]["modified"])

    def test_missing_launcher_is_critical_and_repaired(self):
        (self.bin_dir / "wob").unlink()
        report = self.inspect()
        self.assertIn("launcher.present", self.issue_codes(report))
        result = selfcheck.repair(install_root=self.root, bin_dir=self.bin_dir)
        self.assertTrue(result["success"], result)
        self.assertTrue(any(a["action"] == "rewrite_launchers" for a in result["actions"]))
        self.assertTrue((self.bin_dir / "wob").is_file())
        self.assertEqual(self.inspect()["status"], "healthy")

    def test_stale_launcher_target_is_detected_and_repaired(self):
        launcher = self.bin_dir / "wob"
        text = launcher.read_text().replace(f"APP={self.app_dir}", "APP=/opt/wrong/app")
        launcher.write_text(text)
        launcher.chmod(0o755)
        report = self.inspect()
        finding = next(c for c in report["checks"] if c["code"] == "launcher.present")
        self.assertEqual(finding["status"], "critical")
        self.assertIn("expected", finding["detail"])
        selfcheck.repair(install_root=self.root, bin_dir=self.bin_dir)
        self.assertEqual(self.inspect()["status"], "healthy")

    def test_non_executable_launcher_is_repaired(self):
        launcher = self.bin_dir / "wob"
        launcher.chmod(0o644)
        report = self.inspect()
        finding = next(c for c in report["checks"] if c["code"] == "launcher.present")
        self.assertEqual(finding["status"], "warning")
        selfcheck.repair(install_root=self.root, bin_dir=self.bin_dir)
        self.assertTrue(os.access(launcher, os.X_OK))

    def test_missing_bytecode_is_a_warning_and_recompiled(self):
        for pycache in (self.app_dir / "wobble").rglob("__pycache__"):
            shutil.rmtree(pycache)
        report = self.inspect()
        finding = next(c for c in report["checks"] if c["code"] == "runtime.bytecode")
        self.assertEqual(finding["status"], "warning")
        result = selfcheck.repair(install_root=self.root, bin_dir=self.bin_dir)
        self.assertTrue(any(a["action"] == "compile_bytecode" for a in result["actions"]))
        finding = next(c for c in self.inspect()["checks"] if c["code"] == "runtime.bytecode")
        self.assertEqual(finding["status"], "ok")

    def test_interrupted_install_debris_is_reported_and_removed(self):
        leftover = self.root / ".app.tmp-4242"
        leftover.mkdir()
        (leftover / "junk.txt").write_text("x")
        report = self.inspect()
        self.assertIn("installer.leftovers", self.issue_codes(report))
        result = selfcheck.repair(install_root=self.root, bin_dir=self.bin_dir)
        self.assertFalse(leftover.exists())
        self.assertTrue(any(a["action"] == "cleanup_leftovers" for a in result["actions"]))

    def test_corrupt_config_is_reported_and_backed_up(self):
        config = self.home / ".config" / "wobble" / "config.json"
        config.parent.mkdir(parents=True)
        config.write_text("{broken json")
        report = self.inspect()
        self.assertIn("data.config", self.issue_codes(report))
        result = selfcheck.repair(install_root=self.root, bin_dir=self.bin_dir)
        self.assertTrue(any(a["action"] == "backup_corrupt_config" for a in result["actions"]))
        self.assertFalse(config.exists())
        self.assertTrue(list(config.parent.glob("config.json.corrupt.bak*")))
        self.assertNotIn("data.config", self.issue_codes(self.inspect()))

    def test_unexpected_runtime_file_is_reported(self):
        (self.app_dir / "wobble" / "sneaky.py").write_text("VALUE = 1\n")
        report = self.inspect()
        finding = next(c for c in report["checks"] if c["code"] == "runtime.extras")
        self.assertEqual(finding["status"], "warning")
        self.assertIn("wobble/sneaky.py", finding["data"]["extras"])

    def test_incidents_from_the_ledger_surface_in_status(self):
        health.record_incident("crash", "RuntimeError: boom")
        report = self.inspect()
        finding = next(c for c in report["checks"] if c["code"] == "history.incidents")
        self.assertEqual(finding["status"], "warning")
        self.assertIn("RuntimeError: boom", finding["detail"])
        self.assertEqual(report["incidents"]["total"], 1)

    def test_accept_current_requires_yes_in_json_mode(self):
        target = self.app_dir / "wobble" / "core" / "theme.py"
        target.write_text(target.read_text() + "\n# local patch\n")
        result = self.run_cli("--json", "self", "repair", "--accept-current")
        self.assertEqual(result.returncode, 1)
        # Still damaged: the hashes were not rewritten without explicit consent.
        self.assertFalse(installer.verify(self.root)["ok"])

    def test_manifest_without_hashes_fails_verification(self):
        manifest_file = self.root / "install.json"
        data = json.loads(manifest_file.read_text())
        data["files"] = {}
        manifest_file.write_text(json.dumps(data))
        report = installer.verify(self.root)
        self.assertFalse(report["ok"])
        self.assertEqual(report["error_code"], "installation_manifest_invalid")

    def test_repair_rebuilds_a_deleted_runtime_from_the_snapshot(self):
        shutil.rmtree(self.app_dir)
        result = selfcheck.repair(install_root=self.root, bin_dir=self.bin_dir)
        self.assertTrue(result["success"], result)
        self.assertEqual(result["restore"]["mode"], "full")
        self.assertTrue((self.app_dir / "wobble" / "cli.py").is_file())
        self.assertTrue(installer.verify(self.root)["ok"])

    def test_repair_restores_modified_files_without_hiding_the_damage(self):
        target = self.app_dir / "wobble" / "core" / "theme.py"
        patched = target.read_text() + "\n# local patch\n"
        target.write_text(patched)
        result = selfcheck.repair(install_root=self.root, bin_dir=self.bin_dir)
        self.assertTrue(result["success"], result)
        # The file is restored, not blessed: the local edit is preserved in a
        # backup and the manifest still describes the pristine runtime.
        self.assertNotEqual(target.read_text(), patched)
        self.assertEqual((Path(result["restore"]["backup_dir"]) / "app" / "wobble"
                          / "core" / "theme.py").read_text(), patched)
        self.assertTrue(installer.verify(self.root)["ok"])
        # Explicit opt-in keeps the patch and re-baselines the hashes.
        target.write_text(patched)
        result = selfcheck.repair(install_root=self.root, bin_dir=self.bin_dir,
                                  accept_current=True)
        self.assertTrue(result["success"], result)
        self.assertEqual(target.read_text(), patched)
        self.assertEqual(self.inspect(deep=True)["status"], "healthy")


class TestVerify(SelfCheckBase):
    def test_verify_matches_manifest(self):
        report = installer.verify(self.root)
        self.assertTrue(report["ok"])
        self.assertEqual(report["checked"], report["file_count"])
        self.assertGreater(report["hashed_bytes"], 0)
        self.assertIn("elapsed_ms", report)

    def test_parallel_and_serial_agree(self):
        parallel = installer.verify(self.root, parallel=True)
        serial = installer.verify(self.root, parallel=False)
        self.assertEqual(parallel["checked"], serial["checked"])
        self.assertEqual(parallel["ok"], serial["ok"])

    def test_verify_detects_missing_and_modified(self):
        (self.app_dir / "wobble" / "core" / "theme.py").unlink()
        target = self.app_dir / "wobble" / "core" / "errors.py"
        target.write_text(target.read_text() + "\n# tampered\n")
        report = installer.verify(self.root)
        self.assertFalse(report["ok"])
        self.assertIn("wobble/core/theme.py", report["missing"])
        self.assertIn("wobble/core/errors.py", report["modified"])
        self.assertIn("hint", report)


class TestSelfCli(SelfCheckBase):
    def test_status_json_healthy_exit_zero(self):
        result = self.run_cli("self", "status", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertTrue(data["ok"])
        self.assertEqual(data["mode"], "standalone")
        self.assertIn("checks", data)
        self.assertEqual(data["exit_code"], 0)

    def test_status_json_broken_exit_one(self):
        (self.app_dir / "wobble" / "core" / "theme.py").unlink()
        result = self.run_cli("self", "status", "--json")
        self.assertEqual(result.returncode, 1, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["status"], "broken")
        self.assertIn("runtime.files", {issue["code"] for issue in data["issues"]})

    def test_status_strict_turns_warnings_into_failure(self):
        target = self.app_dir / "wobble" / "core" / "theme.py"
        target.write_text(target.read_text() + "\n# drift\n")
        self.assertEqual(self.run_cli("self", "status", "--json").returncode, 0)
        self.assertEqual(self.run_cli("self", "status", "--json", "--strict").returncode, 1)
        self.assertEqual(self.run_cli("self", "status", "--brief").returncode, 0)

    def test_verify_json_contract_is_preserved(self):
        result = self.run_cli("self", "verify", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertTrue(data["ok"])
        self.assertTrue(data["success"])
        self.assertGreater(data["checked"], 20)

    def test_repair_command_restores_launcher(self):
        (self.bin_dir / "wob").unlink()
        result = self.run_cli("self", "repair")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.bin_dir / "wob").is_file())
        self.assertIn("repaired", result.stdout)

    def test_incidents_command_lists_and_clears(self):
        health.record_incident("crash", "ValueError: sample")
        listed = self.run_cli("--json", "self", "incidents")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        payload = json.loads(listed.stdout)
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["incidents"][0]["kind"], "crash")

        cleared = self.run_cli("--json", "self", "incidents", "--clear")
        self.assertEqual(json.loads(cleared.stdout)["cleared"], 1)
        self.assertEqual(health.read_incidents(), [])

    def test_watch_stops_after_count(self):
        result = self.run_cli("self", "watch", "--interval", "0.2", "--count", "2")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("watching installation health", result.stdout)
        tick_lines = [line for line in result.stdout.splitlines()
                      if line[:2].isdigit() and line[2:3] == ":"]
        self.assertEqual(len(tick_lines), 2)  # one line per tick, no bracket noise

    def test_watch_json_lines(self):
        result = self.run_cli("--json", "self", "watch", "--interval", "0.2", "--count", "2")
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = [json.loads(line) for line in result.stdout.strip().splitlines()]
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]["tick"], 1)
        self.assertIn("changes", lines[0])


if __name__ == "__main__":
    unittest.main()
