"""
Test the standalone installer: layout, manifest, source independence,
integrity verification, foreign-launcher safety, and uninstall behaviour.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from wobble import __version__
from wobble.core import installer

REPO = Path(__file__).resolve().parents[1]


class TestInstaller(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="wobble_install_"))
        self.home = self.tmp / "home"
        self.source = self.tmp / "source"
        self.root = self.tmp / "install"
        self.bin_dir = self.tmp / "bin"
        self.home.mkdir(parents=True)
        self._old_home = os.environ.get("HOME")
        os.environ["HOME"] = str(self.home)

        shutil.copytree(
            REPO / "wobble",
            self.source / "wobble",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )
        license_file = REPO / "LICENSE"
        if license_file.is_file():
            shutil.copy2(license_file, self.source / "LICENSE")

    def tearDown(self):
        if self._old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self._old_home
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- helpers --------------------------------------------------------
    def _install(self, **kwargs):
        options = dict(completions=False, update_path=False)
        options.update(kwargs)
        return installer.install(
            source_root=self.source,
            install_root=self.root,
            bin_dir=self.bin_dir,
            **options,
        )

    def _env(self):
        env = dict(os.environ)
        for key in ("PYTHONPATH", "WOBBLE_INSTALL_DIR", "WOBBLE_BIN_DIR",
                    "WOBBLE_PREFIX_LINK", "PREFIX"):
            env.pop(key, None)
        env["HOME"] = str(self.home)
        return env

    def _run(self, *args):
        return subprocess.run(
            [str(self.bin_dir / "wob"), *args],
            env=self._env(),
            capture_output=True,
            text=True,
            timeout=90,
            cwd=str(self.tmp),
        )

    # -- layout ---------------------------------------------------------
    def test_custom_bin_dir_does_not_write_to_default_bin(self):
        self._install()
        self.assertFalse((self.home / ".local" / "bin" / "wob").exists())

    def test_install_writes_manifest_and_launcher(self):
        data = self._install()
        self.assertTrue((self.root / "install.json").is_file())
        self.assertTrue((self.root / "app" / "wob.py").is_file())
        self.assertTrue((self.root / "app" / "wobble" / "cli.py").is_file())
        self.assertTrue((self.bin_dir / "wob").is_file())
        self.assertTrue(os.access(self.bin_dir / "wob", os.X_OK))
        self.assertEqual(data["version"], __version__)
        self.assertGreater(data["file_count"], 20)
        self.assertTrue(data["standalone"])

        manifest = json.loads((self.root / "install.json").read_text())
        self.assertEqual(manifest["app_dir"], str((self.root / "app").resolve()))
        self.assertEqual(manifest["launcher"], str((self.bin_dir / "wob").resolve()))
        # Bytecode must not be part of the integrity manifest
        self.assertFalse(any("__pycache__" in rel for rel in manifest["files"]))
        # Precompiled bytecode should exist for fast startup
        self.assertTrue(any((self.root / "app" / "wobble").rglob("*.pyc")))

    def test_launcher_survives_source_deletion(self):
        self._install()
        shutil.rmtree(self.source)

        version = self._run("--version")
        self.assertEqual(version.returncode, 0, version.stderr)
        self.assertIn("Wobble v", version.stdout)

        verify = self._run("--json", "self", "verify")
        self.assertEqual(verify.returncode, 0, verify.stderr)
        report = json.loads(verify.stdout)
        self.assertTrue(report["ok"], report)
        self.assertFalse(report["source_exists"])
        self.assertGreater(report["checked"], 20)

        status = self._run("--json", "self", "status")
        data = json.loads(status.stdout)
        self.assertTrue(data["standalone"])
        self.assertTrue(data["installed"])
        self.assertFalse(data["source_exists"])

    def test_verify_detects_tampering(self):
        self._install()
        target = self.root / "app" / "wobble" / "cli.py"
        target.write_text(target.read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8")

        report = installer.verify(self.root)
        self.assertFalse(report["ok"])
        self.assertIn("wobble/cli.py", report["modified"])

    def test_status_reports_missing_manifest(self):
        status = installer.status(self.root)
        self.assertFalse(status["installed"])
        self.assertFalse(status["standalone"])

    # -- safety ---------------------------------------------------------
    def test_refuses_foreign_launcher_without_force(self):
        self.bin_dir.mkdir(parents=True)
        foreign = self.bin_dir / "wob"
        foreign.write_text("#!/bin/sh\necho not-wobble\n", encoding="utf-8")
        foreign.chmod(0o755)

        with self.assertRaises(installer.InstallerError):
            self._install()
        self.assertIn("not-wobble", foreign.read_text())

        data = self._install(force=True)
        self.assertTrue(data["standalone"])
        self.assertIn("Wobble launcher", (self.bin_dir / "wob").read_text())

    def test_refuses_unsafe_install_root(self):
        with self.assertRaises(installer.InstallerError):
            installer.install(
                source_root=self.source,
                install_root=Path("/"),
                bin_dir=self.bin_dir,
                completions=False,
                update_path=False,
            )

    def test_install_rejects_non_wobble_source(self):
        empty = self.tmp / "empty"
        empty.mkdir()
        with self.assertRaises(installer.InstallerError):
            installer.install(
                source_root=empty,
                install_root=self.root,
                bin_dir=self.bin_dir,
                completions=False,
                update_path=False,
            )

    # -- uninstall ------------------------------------------------------
    def test_uninstall_removes_runtime_but_preserves_projects(self):
        self._install()
        project = self.home / "projects" / "demo"
        project.mkdir(parents=True)
        (project / "index.html").write_text("<h1>keep me</h1>")
        data_dir = self.home / ".wobble"
        data_dir.mkdir(parents=True)
        (data_dir / "projects.json").write_text("{}")

        report = installer.uninstall(self.root)

        self.assertTrue(report["success"])
        self.assertFalse((self.root / "app").exists())
        self.assertFalse((self.root / "install.json").exists())
        self.assertFalse((self.bin_dir / "wob").exists())
        self.assertTrue((project / "index.html").is_file())
        self.assertTrue((data_dir / "projects.json").is_file())
        self.assertTrue(report["projects_preserved"])

    def test_uninstall_purge_removes_config(self):
        self._install()
        config = self.home / ".config" / "wobble"
        config.mkdir(parents=True)
        (config / "config.json").write_text("{}")

        report = installer.uninstall(self.root, purge=True)
        self.assertFalse(config.exists())
        self.assertTrue(report["purged"])


class TestShellScripts(unittest.TestCase):
    """The shell entrypoints must refuse obviously unsafe locations."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="wobble_shell_"))
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.env = dict(os.environ)
        self.env["HOME"] = str(self.home)
        for key in ("WOBBLE_INSTALL_DIR", "WOBBLE_BIN_DIR", "WOBBLE_PREFIX_LINK"):
            self.env.pop(key, None)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, script, *args):
        return subprocess.run(
            ["sh", str(REPO / script), *args],
            env=self.env, capture_output=True, text=True, timeout=60, cwd=str(self.tmp),
        )

    def test_uninstall_refuses_root(self):
        result = self._run("uninstall.sh", "--root", "/", "--yes")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Refusing", result.stderr + result.stdout)

    def test_uninstall_ignores_unknown_root(self):
        sentinel = self.tmp / "app"
        sentinel.mkdir()
        (sentinel / "keep.txt").write_text("keep")
        result = self._run("uninstall.sh", "--root", str(self.tmp),
                           "--bin", str(self.tmp / "bin"), "--yes")
        self.assertEqual(result.returncode, 0)
        self.assertTrue((sentinel / "keep.txt").is_file())

    def test_plain_install_sh_uses_local_checkout(self):
        # Reproduce `cd wobble && sh install.sh`: $0 has no slash, so the old
        # launcher-detection logic mistakenly ignored the local checkout.
        result = subprocess.run(
            ["sh", "install.sh",
             "--root", str(self.tmp / "root"), "--bin", str(self.tmp / "bin"),
             "--no-path", "--no-completion"],
            cwd=str(REPO), env=self.env, capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Using local checkout", result.stdout)
        self.assertTrue((self.tmp / "bin" / "wob").is_file())

    def test_install_refuses_root(self):
        result = self._run("install.sh", "--root", "/", "--bin", str(self.tmp / "bin"),
                           "--no-path", "--no-completion")
        self.assertNotEqual(result.returncode, 0)


class TestInstallerHelpers(unittest.TestCase):
    def test_launcher_script_has_no_source_reference(self):
        script = installer._launcher_script(Path("/opt/wobble/app"), "/usr/bin/python3")
        self.assertIn("Wobble launcher", script)
        self.assertIn("APP=/opt/wobble/app", script)
        self.assertIn('"$PY" "$APP/wob.py" "$@"', script)
        self.assertNotIn("PYTHONPATH", script)

    def test_launcher_can_self_heal(self):
        script = installer._launcher_script(Path("/opt/wobble/app"), "/usr/bin/python3")
        self.assertIn('ROOT=/opt/wobble', script)
        self.assertIn('RESCUE="$ROOT/rescue.sh"', script)
        self.assertIn("WOBBLE_AUTO_RESCUE", script)
        # Only the dedicated runtime-load code triggers recovery, so a command
        # that legitimately exits non-zero is never run twice.
        self.assertIn('[ "$status" -eq 121 ]', script)

    def test_package_root_is_repository(self):
        self.assertTrue((installer.package_root() / "wobble" / "cli.py").is_file())


if __name__ == "__main__":
    unittest.main()
