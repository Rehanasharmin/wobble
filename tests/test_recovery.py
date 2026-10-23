"""Self-healing: offline snapshots, runtime restore, rescue scripts, and the
CLI contract around ``wob self repair`` / ``wob self rescue`` / ``wob-rescue``.
"""

import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

from wobble import __version__
from wobble.core import installer, recovery, selfcheck

REPO = Path(__file__).resolve().parents[1]


class RecoveryBase(unittest.TestCase):
    """Install Wobble into a throwaway prefix and hand back the paths."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="wobble_recovery_"))
        self.home = self.tmp / "home"
        self.root = self.tmp / "root"
        self.bin_dir = self.tmp / "bin"
        self.source = self.tmp / "source"
        self.home.mkdir(parents=True)

        # A private source checkout so "source is gone" can be tested honestly.
        shutil.copytree(
            REPO / "wobble", self.source / "wobble",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )
        for extra in ("LICENSE", "README.md"):
            if (REPO / extra).is_file():
                shutil.copy2(REPO / extra, self.source / extra)

        self._env_backup = {key: os.environ.get(key) for key in
                            ("HOME", "WOBBLE_INSTALL_DIR", "WOBBLE_BIN_DIR",
                             "PYTHONPATH", "PATH")}
        os.environ["HOME"] = str(self.home)
        os.environ["WOBBLE_INSTALL_DIR"] = str(self.root)
        os.environ["WOBBLE_BIN_DIR"] = str(self.bin_dir)
        os.environ["PATH"] = f"{self.bin_dir}:{os.environ.get('PATH', '')}"
        os.environ.pop("PYTHONPATH", None)

        self.data = installer.install(
            source_root=self.source,
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
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- helpers --------------------------------------------------------
    def env(self, **overrides):
        env = dict(os.environ)
        env["HOME"] = str(self.home)
        env["WOBBLE_INSTALL_DIR"] = str(self.root)
        env["WOBBLE_BIN_DIR"] = str(self.bin_dir)
        env["PATH"] = f"{self.bin_dir}:{env.get('PATH', '')}"
        env.pop("PYTHONPATH", None)
        env.update(overrides)
        return env

    def run_wob(self, *args, **kwargs):
        """Run the *installed launcher*, so the self-healing wrapper is exercised."""
        return subprocess.run(
            [str(self.bin_dir / "wob"), *args],
            env=self.env(**kwargs.pop("env", {})),
            capture_output=True, text=True, timeout=120, cwd=str(self.tmp),
            **kwargs,
        )

    def run_cli(self, *args):
        """Run the CLI from the repo checkout (works when the install is gone)."""
        return subprocess.run(
            [sys.executable, "-m", "wobble", *args],
            env=self.env(PYTHONPATH=str(REPO)),
            capture_output=True, text=True, timeout=120, cwd=str(REPO),
        )

    def run_rescue(self, *args, **kwargs):
        return subprocess.run(
            [str(self.bin_dir / "wob-rescue"), *args],
            env=self.env(**kwargs.pop("env", {})),
            capture_output=True, text=True, timeout=120, cwd=str(self.tmp),
            **kwargs,
        )

    def repair(self, **kwargs):
        return selfcheck.repair(install_root=self.root, bin_dir=self.bin_dir, **kwargs)

    def corrupt(self, rel="wobble/core/theme.py", text="\n# local junk\n"):
        target = self.app_dir / rel
        target.write_text(target.read_text() + text)
        return target

    def damage_source_and_snapshot(self):
        """Remove every recovery source so 'nothing to restore from' is real."""
        shutil.rmtree(self.root / "snapshot")
        shutil.rmtree(self.source)


class TestSnapshotAssets(RecoveryBase):
    def test_install_writes_a_verified_snapshot(self):
        self.assertTrue(recovery.snapshot_app_dir(self.root).is_dir())
        self.assertTrue(recovery.snapshot_manifest_path(self.root).is_file())
        report = recovery.verify_snapshot(self.root)
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["file_count"], self.data["file_count"])
        self.assertGreater(report["checked"], 20)

    def test_snapshot_excludes_bytecode(self):
        names = [p.name for p in recovery.snapshot_app_dir(self.root).rglob("*")
                 if p.is_file()]
        self.assertFalse([n for n in names if n.endswith(".pyc")])
        self.assertIn("wob.py", names)

    def test_rescue_assets_are_installed(self):
        self.assertTrue(recovery.rescue_py_path(self.root).is_file())
        self.assertTrue(recovery.rescue_sh_path(self.root).is_file())
        self.assertTrue((self.bin_dir / "wob-rescue").is_file())
        self.assertTrue(os.access(str(self.bin_dir / "wob-rescue"), os.X_OK))
        manifest = installer.read_manifest(self.root)
        self.assertTrue(manifest["snapshot"]["ok"])
        self.assertIn(str(self.bin_dir / "wob-rescue"), manifest["rescue_launchers"])

    def test_status_reports_the_snapshot(self):
        report = selfcheck.inspect(install_root=self.root, bin_dir=self.bin_dir)
        check = next(c for c in report["checks"] if c["code"] == "recovery.snapshot")
        self.assertEqual(check["status"], "ok")
        self.assertIn("files", check["detail"])
        self.assertTrue(check["data"]["valid"])

    def test_status_warns_when_the_snapshot_is_missing(self):
        shutil.rmtree(self.root / "snapshot")
        report = selfcheck.inspect(install_root=self.root, bin_dir=self.bin_dir)
        check = next(c for c in report["checks"] if c["code"] == "recovery.snapshot")
        self.assertEqual(check["status"], "warning")
        self.assertIn("--snapshot", check["fix"])

    def test_uninstall_removes_recovery_assets(self):
        installer.uninstall(install_root=self.root, purge=False)
        self.assertFalse((self.root / "snapshot").exists())
        self.assertFalse((self.root / "rescue.py").exists())
        self.assertFalse((self.root / "rescue.sh").exists())
        self.assertFalse((self.bin_dir / "wob-rescue").exists())


class TestRestore(RecoveryBase):
    def test_modified_file_is_restored_and_the_damaged_copy_kept(self):
        target = self.corrupt()
        patched = target.read_text()
        result = self.repair()
        self.assertTrue(result["success"], result)
        self.assertNotEqual(target.read_text(), patched)
        self.assertTrue(installer.verify(self.root)["ok"])
        restore = result["restore"]
        self.assertEqual(restore["mode"], "partial")
        self.assertEqual(restore["modified"], ["wobble/core/theme.py"])
        backup_file = Path(restore["backup_dir"]) / "app" / "wobble" / "core" / "theme.py"
        self.assertTrue(backup_file.is_file())
        self.assertEqual(backup_file.read_text(), patched)
        self.assertEqual(result["restore"]["source"]["kind"], "snapshot")

    def test_deleted_file_is_restored(self):
        (self.app_dir / "wobble" / "core" / "probecache.py").unlink()
        result = self.repair()
        self.assertTrue(result["success"], result)
        self.assertTrue((self.app_dir / "wobble" / "core" / "probecache.py").is_file())
        self.assertTrue(installer.verify(self.root)["ok"])

    def test_deleted_runtime_is_reinstalled_from_the_snapshot(self):
        shutil.rmtree(self.app_dir)
        shutil.rmtree(self.source)
        result = self.repair()
        self.assertTrue(result["success"], result)
        self.assertEqual(result["restore"]["mode"], "full")
        self.assertTrue((self.app_dir / "wob.py").is_file())
        self.assertTrue(installer.verify(self.root)["ok"])
        self.assertEqual(self.run_wob("--version").returncode, 0)

    def test_corrupt_manifest_is_preserved_and_rebuilt(self):
        manifest_file = self.root / "install.json"
        manifest_file.write_text("{ this is not json")
        result = self.repair()
        self.assertTrue(result["success"], result)
        self.assertTrue(any(a["action"] == "backup_corrupt_manifest"
                            for a in result["actions"]))
        self.assertTrue(any(a["action"] == "rebuild_manifest" for a in result["actions"]))
        self.assertEqual(manifest_file.read_text().strip()[0], "{")
        manifest = installer.read_manifest(self.root)
        self.assertEqual(manifest["file_count"], self.data["file_count"])
        self.assertTrue(installer.verify(self.root)["ok"])

    def test_missing_manifest_is_rebuilt_from_disk(self):
        (self.root / "install.json").unlink()
        result = self.repair()
        self.assertTrue(result["success"], result)
        self.assertTrue(installer.read_manifest(self.root))
        self.assertTrue(installer.verify(self.root)["ok"])
        self.assertEqual(self.run_wob("--version").returncode, 0)

    def test_manifest_cannot_aim_the_restore_outside_the_install_root(self):
        other = self.tmp / "elsewhere"
        other.mkdir()
        manifest_file = self.root / "install.json"
        data = json.loads(manifest_file.read_text())
        data["app_dir"] = str(other)
        manifest_file.write_text(json.dumps(data))
        self.corrupt()
        result = self.repair()
        self.assertTrue(result["success"], result)
        self.assertEqual(list(other.iterdir()), [])
        self.assertTrue(any(w.get("action") == "resolve_app_dir"
                            for w in result["warnings"]))
        repaired = json.loads(manifest_file.read_text())
        self.assertEqual(Path(repaired["app_dir"]), self.app_dir)

    def test_dry_run_changes_nothing(self):
        target = self.corrupt()
        before = target.read_text()
        result = self.repair(dry_run=True)
        self.assertTrue(result["success"], result)
        self.assertTrue(result["dry_run"])
        self.assertEqual(target.read_text(), before)
        self.assertIn("wobble/core/theme.py", result["plan"]["restore"])
        self.assertEqual(result["plan"]["source"]["kind"], "snapshot")
        self.assertFalse(installer.verify(self.root)["ok"])

    def test_no_backup_flag_skips_the_copy(self):
        self.corrupt()
        result = self.repair(backup=False)
        self.assertTrue(result["success"], result)
        self.assertFalse((self.root / "repair-backups").exists())

    def test_only_damaged_files_are_touched(self):
        keeper = self.app_dir / "wobble" / "core" / "logger.py"
        keeper_stat = keeper.stat()
        self.corrupt()
        result = self.repair()
        self.assertTrue(result["success"])
        self.assertEqual(keeper.stat().st_mtime, keeper_stat.st_mtime)
        self.assertEqual(len(result["restore"]["restored"]), 1)

    def test_accept_current_keeps_the_patch_and_rebaselines_everything(self):
        target = self.corrupt()
        patched = target.read_text()
        result = self.repair(accept_current=True)
        self.assertTrue(result["success"], result)
        self.assertEqual(target.read_text(), patched)
        self.assertTrue(installer.verify(self.root)["ok"])
        self.assertTrue(recovery.verify_snapshot(self.root)["ok"])
        self.assertTrue((recovery.snapshot_app_dir(self.root) / "wobble" / "core"
                         / "theme.py").read_text().endswith("# local junk\n"))

    def test_repair_is_idempotent(self):
        self.corrupt()
        first = self.repair()
        self.assertTrue(first["success"], first)
        second = self.repair()
        self.assertTrue(second["success"], second)
        self.assertEqual(second["restore"]["mode"], "none")
        self.assertFalse(any(a["action"] == "restore_runtime"
                             for a in second["actions"]))

    def test_no_source_and_no_snapshot_fails_honestly(self):
        self.damage_source_and_snapshot()
        self.corrupt("wobble/android/limitations.py")
        result = self.run_wob("--json", "self", "repair")
        data = json.loads(result.stdout)
        self.assertEqual(result.returncode, 1, data)
        failure = next(f for f in data["failed"] if f["action"] == "restore_runtime")
        self.assertEqual(failure["error_code"], "recovery_source_unavailable")
        self.assertIn("No verified recovery source", failure["error"])
        self.assertTrue(data["unresolved"])

    def test_source_checkout_is_used_when_the_snapshot_is_gone(self):
        shutil.rmtree(self.root / "snapshot")
        self.corrupt()
        result = self.repair()
        self.assertTrue(result["success"], result)
        self.assertEqual(result["restore"]["source"]["kind"], "source")
        self.assertTrue(installer.verify(self.root)["ok"])

    def test_damaged_snapshot_is_not_used_as_a_source(self):
        snapshot_file = recovery.snapshot_app_dir(self.root) / "wobble" / "core" / "logger.py"
        snapshot_file.write_text("broken snapshot\n")
        self.corrupt()
        result = self.repair()
        self.assertTrue(result["success"], result)
        self.assertEqual(result["restore"]["source"]["kind"], "source")
        # The snapshot is rebuilt from the now-verified runtime.
        self.assertTrue(recovery.verify_snapshot(self.root)["ok"])

    def test_version_drift_is_rejected_unless_forced(self):
        manifest_file = self.root / "install.json"
        data = json.loads(manifest_file.read_text())
        data["version"] = "0.0.1"
        manifest_file.write_text(json.dumps(data))
        snapshot_manifest = recovery.read_snapshot_manifest(self.root)[0]
        snapshot_manifest["version"] = "0.0.1"
        recovery.snapshot_manifest_path(self.root).write_text(json.dumps(snapshot_manifest))
        with self.assertRaises(recovery.RecoveryError):
            recovery.select_source(self.root, data, target_version="9.9.9")
        chosen = recovery.select_source(self.root, data, target_version="9.9.9",
                                         allow_version_drift=True)
        self.assertEqual(chosen["kind"], "snapshot")


class TestLauncherSelfHealing(RecoveryBase):
    def test_deleted_module_is_restored_before_the_command_runs(self):
        (self.app_dir / "wobble" / "cli.py").unlink()
        result = self.run_wob("about")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("wobble v", result.stdout.lower())
        self.assertIn("restoring the runtime", result.stderr)
        self.assertTrue((self.app_dir / "wobble" / "cli.py").is_file())
        self.assertTrue(installer.verify(self.root)["ok"])

    def test_broken_syntax_is_healed_by_the_launcher(self):
        (self.app_dir / "wobble" / "core" / "theme.py").write_text("def broken(:\n")
        result = self.run_wob("about")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(installer.verify(self.root)["ok"])

    def test_auto_rescue_can_be_disabled(self):
        (self.app_dir / "wobble" / "cli.py").unlink()
        result = self.run_wob("about", env={"WOBBLE_AUTO_RESCUE": "0"})
        self.assertEqual(result.returncode, 121)
        self.assertFalse((self.app_dir / "wobble" / "cli.py").exists())

    def test_launcher_reports_honestly_without_a_snapshot(self):
        self.damage_source_and_snapshot()
        (self.app_dir / "wobble" / "cli.py").unlink()
        result = self.run_wob("about")
        self.assertEqual(result.returncode, 121)
        self.assertIn("could not restore", result.stderr)

    def test_healthy_commands_never_trigger_recovery(self):
        result = self.run_wob("self", "status", "--brief")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("restoring the runtime", result.stderr)
        self.assertFalse((self.root / "repair-backups").exists())

    def test_rescue_launcher_restores_a_deleted_runtime(self):
        shutil.rmtree(self.app_dir)
        result = self.run_rescue()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("restored", result.stdout)
        self.assertTrue((self.app_dir / "wob.py").is_file())
        self.assertEqual(self.run_wob("--version").returncode, 0)

    def test_rescue_dry_run_does_not_touch_the_runtime(self):
        shutil.rmtree(self.app_dir)
        result = self.run_rescue("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.strip())
        self.assertFalse(self.app_dir.exists())

    def test_shell_rescue_works_without_the_python_helper(self):
        (self.app_dir / "wobble" / "cli.py").unlink()
        (self.root / "rescue.py").rename(self.root / "rescue.py.disabled")
        try:
            result = subprocess.run(
                ["sh", str(self.root / "rescue.sh"), "--quiet"],
                env=self.env(), capture_output=True, text=True, timeout=120,
            )
        finally:
            (self.root / "rescue.py.disabled").rename(self.root / "rescue.py")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.app_dir / "wob.py").is_file())
        self.assertTrue((self.root / "repair-backups").is_dir())


class TestRecoveryPrimitives(RecoveryBase):
    def test_create_snapshot_refuses_a_damaged_runtime(self):
        self.corrupt()
        manifest = installer.read_manifest(self.root)
        with self.assertRaises(recovery.RecoveryError):
            recovery.create_snapshot(self.root, app_dir=self.app_dir,
                                     trusted_files=manifest["files"])

    def test_validate_tree_catches_syntax_errors(self):
        tree = self.tmp / "broken-tree"
        shutil.copytree(self.source, tree)
        (tree / "wobble" / "core" / "theme.py").write_text("def broken(:\n")
        problems = recovery.validate_tree(tree)
        self.assertTrue(any("theme.py" in p for p in problems), problems)

    def test_hash_tree_skips_bytecode(self):
        files, _total = recovery._hash_tree(self.app_dir)
        self.assertFalse([rel for rel in files if rel.endswith(".pyc")])
        self.assertIn("wob.py", files)

    def test_prune_backups_keeps_the_newest(self):
        base = recovery.backups_dir(self.root)
        for index in range(7):
            (base / f"2026010{index}T000000Z" / "app").mkdir(parents=True)
        removed = recovery.prune_backups(self.root, keep=3)
        remaining = sorted(p.name for p in base.iterdir())
        self.assertEqual(len(remaining), 3)
        self.assertEqual(remaining, ["20260104T000000Z", "20260105T000000Z",
                                     "20260106T000000Z"])
        self.assertEqual(len(removed), 4)

    def test_rebuild_manifest_reports_unverified_files(self):
        (self.root / "install.json").unlink()
        result = recovery.rebuild_manifest(self.root, app_dir=self.app_dir,
                                           trusted={}, note="test")
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["file_count"], self.data["file_count"])
        manifest = installer.read_manifest(self.root)
        self.assertEqual(manifest["rebuilt_reason"], "test")
        self.assertIn("manifest_rebuilt_at", manifest)

    def test_expected_files_prefers_the_install_manifest(self):
        manifest = {"files": {"a.py": {"sha256": "1", "size": 1}}}
        snapshot = {"files": {"a.py": {"sha256": "2", "size": 2},
                              "b.py": {"sha256": "3", "size": 3}}}
        merged = recovery.expected_files(manifest, snapshot)
        self.assertEqual(merged["a.py"]["sha256"], "1")
        self.assertIn("b.py", merged)

    def test_readiness_summary_reports_offline_capability(self):
        readiness = recovery.recovery_readiness(self.root,
                                                installer.read_manifest(self.root))
        self.assertTrue(readiness["offline_ready"])
        self.assertTrue(readiness["snapshot"]["valid"])
        self.assertIn("rescue.sh", readiness["command"])


class TestArchiveHandling(RecoveryBase):
    def _make_tar(self, members):
        archive = self.tmp / "crafted.tar.gz"
        payload = self.tmp / "payload"
        payload.mkdir(exist_ok=True)
        (payload / "good.py").write_text("print('ok')\n")
        with tarfile.open(archive, "w:gz") as tar:
            for name, kind in members:
                info = tarfile.TarInfo(name)
                if kind == "symlink":
                    info.type = tarfile.SYMTYPE
                    info.linkname = "/etc/passwd"
                    tar.addfile(info)
                elif kind == "dir":
                    info.type = tarfile.DIRTYPE
                    tar.addfile(info)
                else:
                    data = b"export\n"
                    info.size = len(data)
                    import io
                    tar.addfile(info, io.BytesIO(data))
        return archive

    def test_extraction_rejects_path_traversal(self):
        archive = self._make_tar([
            ("pkg-1.0/../../evil.sh", "file"),
            ("pkg-1.0/ok.sh", "file"),
        ])
        dest = self.tmp / "extract-traversal"
        with self.assertRaises(recovery.RecoveryError):
            recovery._extract_archive(archive, dest)
        self.assertFalse((self.tmp / "evil.sh").exists())

    def test_extraction_skips_symlinks_and_finds_the_tree(self):
        archive = self._make_tar([
            ("pkg-1.0/wobble/__init__.py", "file"),
            ("pkg-1.0/wobble/bootstrap.py", "file"),
            ("pkg-1.0/wobble/cli.py", "file"),
            ("pkg-1.0/link", "symlink"),
        ])
        dest = self.tmp / "extract-links"
        tree = recovery._extract_archive(archive, dest)
        self.assertTrue((tree / "wobble" / "cli.py").is_file())
        self.assertFalse((tree / "link").exists())

    def test_download_supports_file_urls(self):
        source = self.tmp / "download-source.tar.gz"
        with tarfile.open(source, "w:gz") as tar:
            tar.add(self.source / "wobble", arcname=f"wobble-{__version__}/wobble")
        fetched = recovery._download(f"file://{source}")
        try:
            self.assertTrue(fetched.is_file())
            self.assertGreater(fetched.stat().st_size, 0)
        finally:
            fetched.unlink(missing_ok=True)

    def test_default_urls_prefer_the_release_tag(self):
        urls = recovery._default_urls(__version__)
        self.assertIn("/refs/tags/v" + __version__, urls[0])
        self.assertTrue(urls[-1].endswith("/refs/heads/main"))


class TestRepairCli(RecoveryBase):
    def _json(self, *args):
        result = self.run_wob("--json", *args)
        self.assertTrue(result.stdout.strip().startswith("{"), result.stdout + result.stderr)
        return result, json.loads(result.stdout)

    def test_repair_json_restores_and_reports(self):
        self.corrupt("wobble/core/probecache.py")
        result, data = self._json("self", "repair")
        self.assertEqual(result.returncode, 0, data)
        self.assertTrue(data["success"])
        restore = next(a for a in data["actions"] if a["action"] == "restore_runtime")
        self.assertEqual(restore["mode"], "partial")
        self.assertTrue(data["verification"]["ok"])

    def test_repair_dry_run_json_has_a_plan(self):
        self.corrupt()
        result, data = self._json("self", "repair", "--dry-run")
        self.assertEqual(result.returncode, 0, data)
        self.assertTrue(data["dry_run"])
        self.assertTrue(data["plan"]["restore"])

    def test_rescue_json_contract(self):
        self.corrupt()
        result, data = self._json("self", "rescue")
        self.assertEqual(result.returncode, 0, data)
        self.assertTrue(data["success"])
        self.assertTrue(data["emergency"])

    def test_top_level_rescue_alias(self):
        self.corrupt()
        result, data = self._json("rescue")
        self.assertEqual(result.returncode, 0, data)
        self.assertTrue(data["success"])

    def test_repair_human_output_mentions_backup(self):
        self.corrupt()
        result = self.run_wob("self", "repair")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("restored 1 file(s) from snapshot", result.stdout)
        self.assertIn("backup", result.stdout)

    def test_status_deep_flags_the_damage_and_suggests_repair(self):
        self.corrupt()
        result = self.run_wob("self", "status", "--deep")
        self.assertIn("self repair", result.stdout)

    def test_repair_without_manifest_or_snapshot_fails_with_install_hint(self):
        shutil.rmtree(self.root / "snapshot")
        shutil.rmtree(self.app_dir)
        (self.root / "install.json").unlink()
        shutil.rmtree(self.source)
        result = self.run_cli("--json", "self", "repair")
        data = json.loads(result.stdout)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(data["success"])
        self.assertEqual(data["error_code"], "installation_manifest_missing")
        self.assertIn("install.sh", data["fix"])


class TestUnwritableInstall(RecoveryBase):
    """Restoring must never destroy the only copy of a damaged file."""

    def _skip_if_root(self):
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("permission failures do not apply to root")

    def test_restore_aborts_when_the_backup_cannot_be_written(self):
        self._skip_if_root()
        target = self.corrupt()
        patched = target.read_text()
        os.chmod(self.root, 0o500)
        try:
            result = self.repair()
        finally:
            os.chmod(self.root, 0o755)
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "recovery_backup_failed")
        self.assertIn("nothing was changed", result["error"])
        self.assertEqual(target.read_text(), patched)

    def test_restore_reports_files_it_cannot_write(self):
        self._skip_if_root()
        target = self.corrupt()
        patched = target.read_text()
        os.chmod(self.app_dir / "wobble" / "core", 0o500)
        try:
            result = self.repair()
        finally:
            os.chmod(self.app_dir / "wobble" / "core", 0o755)
        self.assertFalse(result["success"])
        failure = next(f for f in result["failed"] if f["action"] == "restore_runtime")
        self.assertEqual(failure["error_code"], "recovery_write_failed")
        self.assertEqual(target.read_text(), patched)


class TestRescueFallbacks(RecoveryBase):
    def test_python_fallback_restores_when_the_package_cannot_be_imported(self):
        # A broken package __init__ makes `from wobble.core import recovery`
        # impossible, so rescue.py must fall back to its own stdlib restore.
        (self.app_dir / "wobble" / "__init__.py").write_text("broken (: \n")
        self.assertFalse((self.app_dir / "wobble" / "cli.py").exists() is False)
        result = self.run_wob("--version")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("restored", result.stderr)
        self.assertTrue(installer.verify(self.root)["ok"])

    def test_wob_rescue_json_reports_the_fallback_mode(self):
        shutil.rmtree(self.app_dir)
        result = self.run_rescue("--json")
        data = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0, data)
        self.assertTrue(data["success"])
        self.assertTrue(data["restored"] or data.get("mode") == "full")

    def test_rescue_refuses_without_a_snapshot(self):
        self.damage_source_and_snapshot()
        shutil.rmtree(self.app_dir)
        result = self.run_rescue()
        self.assertEqual(result.returncode, 1)
        self.assertIn("no offline snapshot", result.stderr.lower() + result.stdout.lower())


class TestInstallWithoutSnapshot(RecoveryBase):
    def setUp(self):
        super().setUp()
        shutil.rmtree(self.root / "snapshot")
        self.data = installer.install(
            source_root=self.source, install_root=self.root, bin_dir=self.bin_dir,
            completions=False, update_path=False, snapshot=False,
        )

    def test_no_snapshot_is_written(self):
        self.assertFalse((self.root / "snapshot").exists())
        self.assertTrue(self.data["snapshot"]["skipped"])

    def test_status_warns_and_repair_still_uses_the_source_checkout(self):
        report = selfcheck.inspect(install_root=self.root, bin_dir=self.bin_dir)
        check = next(c for c in report["checks"] if c["code"] == "recovery.snapshot")
        self.assertEqual(check["status"], "warning")
        self.corrupt()
        result = selfcheck.repair(install_root=self.root, bin_dir=self.bin_dir)
        self.assertTrue(result["success"], result)
        self.assertEqual(result["restore"]["source"]["kind"], "source")
        # Repair rebuilds the missing safety net.
        self.assertTrue(recovery.verify_snapshot(self.root)["ok"])


class TestSourceLadder(RecoveryBase):
    def test_select_source_prefers_the_snapshot(self):
        source = recovery.select_source(self.root, installer.read_manifest(self.root))
        self.assertEqual(source["kind"], "snapshot")
        self.assertEqual(source["version"], __version__)

    def test_select_source_never_returns_the_damaged_runtime(self):
        manifest = installer.read_manifest(self.root)
        manifest["source"] = str(self.app_dir)
        chosen = recovery.select_source(self.root, manifest, prefer="source")
        self.assertNotEqual(chosen["path"], str(self.app_dir))

    def test_unknown_preference_is_rejected(self):
        with self.assertRaises(recovery.RecoveryError):
            recovery.select_source(self.root, {}, prefer="floppy")

    def test_auto_mode_never_downloads_without_permission(self):
        from unittest import mock

        self.damage_source_and_snapshot()
        with mock.patch.object(recovery, "_network_source",
                               side_effect=AssertionError("network used")) as fetch:
            source = recovery.select_source(self.root, {}, prefer="auto", network=False)
        self.assertFalse(fetch.called)
        self.assertNotEqual(source["kind"], "network")
        with mock.patch.object(recovery, "_network_source",
                               side_effect=AssertionError("network used")) as fetch:
            with self.assertRaises(recovery.RecoveryError):
                recovery.select_source(self.root, {}, prefer="snapshot")
        self.assertFalse(fetch.called)

    def test_status_json_exposes_recovery_readiness(self):
        result = self.run_wob("--json", "self", "status")
        data = json.loads(result.stdout)
        check = next(c for c in data["checks"] if c["code"] == "recovery.snapshot")
        self.assertTrue(check["data"]["valid"])
        self.assertTrue(check["data"]["rescue_shell"])
        self.assertIn("rescue.sh", check["data"]["rescue_command"])

    def test_snapshot_preference_does_not_fall_back(self):
        shutil.rmtree(self.root / "snapshot")
        with self.assertRaises(recovery.RecoveryError):
            recovery.select_source(self.root, {}, prefer="snapshot")


if __name__ == "__main__":
    unittest.main()
