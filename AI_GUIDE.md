# Wobble AI Agent Guide (`AI_GUIDE.md`)

This guide is designed for **AI coding agents** (Antigravity, Claude, Codex, Gemini, Cursor, Aider, etc.) operating in or pair-programming within **Termux on Android**. It explains how to interact with Wobble safely, discover project state, execute builds, inspect APKs, run web dev servers, and handle error recovery.

---

## 1. Core Operating Principles for AI Agents

1. **Always use `--json` for Machine Consumption**:
   Every inspection command supports `--json`. AI agents should avoid scraping ANSI or colored text outputs.
   ```bash
   wob doctor --json
   wob project list --json
   wob project info --json
   wob apk list --json
   wob apk info --json
   wob plugin list --json
   wob schema
   ```

2. **Never Assume Root or ADB**:
   - Do NOT execute `su` or assume superuser privileges exist.
   - Do NOT assume `adb` or Shizuku is configured unless confirmed by `wob doctor --json`.
   - On-device installation relies on standard Android system intents dispatched via `wob apk install`.

3. **Respect Android OS W^X Constraints**:
   - Never write executable binaries or scripts to `/sdcard` or shared storage.
   - All source code and build tools must stay within `$HOME` or `$PREFIX`.

4. **Resource Awareness (RAM & OOM)**:
   - Termux runs under Android process restrictions. If building large Android projects with Gradle, ensure `--no-daemon` is passed and memory limits (`-Xmx1024m`) are respected.

---

## 2. Introspecting Wobble Capabilities: `wob schema`

Before executing actions, an AI agent should fetch Wobble's full capability schema:
```bash
wob schema
```
This returns a JSON document detailing:
- CLI command arguments and flags
- Host system environment details (architecture, Termux prefix, storage, RAM)
- Available framework plugins
- Supported package managers and build capabilities

---

## 3. Project Structure & `wobble.json`

Every Wobble project has a root `wobble.json` file. AI agents should read or validate this file:

```json
{
  "name": "myapp",
  "version": "0.1.0",
  "type": "android",
  "framework": "android",
  "description": "Android application built with Wobble on Termux",
  "wobble_version": "1.3.0",
  "created_at": "2026-10-03T05:40:00Z",
  "package_id": "com.example.myapp",
  "scripts": {
    "build": "wob android build",
    "clean": "wob android clean",
    "apk": "wob apk info",
    "install": "wob apk install"
  },
  "dependencies": {
    "system": ["openjdk-17", "aapt", "aapt2", "apksigner"],
    "project": {
      "compileSdk": 34,
      "minSdk": 24
    }
  }
}
```

### Auto-Detection Rules
If `wobble.json` is missing in an existing workspace, Wobble infers the project type:
- Android: Presence of `build.gradle`, `app/build.gradle`, or `AndroidManifest.xml`.
- Web: Presence of `package.json`, `index.html`, `vite.config.js`, `app.py`, or `index.php`.

---

## 4. CLI Commands Reference for AI Agents

| Task | Human Command | Agent / JSON Command | Notes |
|------|---------------|----------------------|-------|
| Check System Health | `wob doctor` | `wob doctor --json` | Cached probes, actionable fixes, and `regressions`/`recovered` since the last run |
| Fast Health Check | `wob doctor --quick` | `wob doctor --json --quick` | Skips subprocess version probes (PATH lookups only) |
| Filter Health Checks | `wob doctor --only android` | `wob doctor --json --only android,wobble` | Categories: `system`, `resources`, `environment`, `tools`, `web`, `android`, `wobble` |
| Health For CI | `wob doctor --strict` | `wob doctor --json --fail-on missing` | Non-zero exit at or above the requested severity; JSON includes `exit_code` |
| Check Installation | `wob self status` | `wob self status --json` | Structured checks with stable `code` values, health `score`, `issues`, and `next_steps` |
| Deep Installation Check | `wob self status --deep` | `wob self status --deep --json` | Adds SHA-256 verification and an import smoke test of core modules |
| Verify Installation | `wob self verify` | `wob self verify --json` | Hashes installed files; `ok=false` plus `missing`/`modified` on damage |
| Repair Installation | `wob self repair` | `wob self repair --json` | Restores missing/corrupted runtime files from the SHA-256-verified snapshot, rebuilds a corrupt manifest, then fixes launchers, bytecode, completions, debris, and config. Damaged files are backed up; integrity is never faked |
| Preview A Repair | `wob self repair --dry-run` | `wob self repair --dry-run --json` | Returns a `plan` (files, source, backup) without changing anything |
| Emergency Recovery | `wob self rescue` / `wob rescue` | `wob self rescue --json` | Full restore from any available source (snapshot, source checkout, downloaded release); tolerates version drift |
| Restore Offline Only | `wob self repair --from snapshot` | `wob self repair --from snapshot --json` | Never falls back to another source; fails with `recovery_source_unavailable` |
| Rebuild The Snapshot | `wob self repair --snapshot` | `wob self repair --snapshot --json` | Re-snapshots a runtime that was patched on purpose (usually after `--accept-current --yes`) |
| Watch For Breakage | `wob self watch --interval 2` | `wob --json self watch` | Prints only changes; JSON mode emits one document per line |
| Read Failure Ledger | `wob self incidents` | `wob self incidents --json` | Recent crashes with counts, timestamps, and messages (`--clear` resets) |
| List Projects | `wob project list` | `wob project list --json` | Lists registered and scanned projects |
| Project Info | `wob project info` | `wob project info --json` | Returns file metrics and configuration |
| Create Android Project | `wob create android <name>` | `wob create android <name> --package <pkg>` | Scaffolds build.gradle, Java, Layout, Manifest |
| Create Web Project | `wob create web <name>` | `wob create web <name> --framework <fw>` | Frameworks: `vite`, `react`, `vue`, `svelte`, `nextjs`, `python`, `php`, `static` |
| Build APK | `wob apk build` | `wob apk build --json` | Executes Gradle build and locates APK |
| List APKs | `wob apk list` | `wob apk list --json` | Finds all APK files in build outputs |
| Inspect APK | `wob apk info <file>` | `wob apk info <file> --json` | Returns package, SDKs, DEX, SHA256, permissions |
| Install APK | `wob apk install <file>` | `wob apk install <file> --json` | Dispatches Android package installer intent |
| Install Dependencies | `wob deps install` | `wob deps install <stack>` | Stacks: `android`, `android-sdk`, `node`, `python`, `php` |
| Add Dependency | `wob deps add <pkg>` | `wob deps add <pkg> -m <mgr>` | Managers: `termux`, `npm`, `pip`, `composer` |
| Start Web Dev Server | `wob web dev` | `wob web dev --port 3000` | Localhost only by default; add `--lan` to expose on Wi-Fi |
| Web Preview (Local) | `wob web preview` | `wob web preview --port 3000` | Hardened static server on `127.0.0.1` |
| Web Preview (LAN) | `wob web preview --lan` | `wob web preview --lan --json` | Prints LAN URL and `lan_enabled: true`; use only on trusted networks |

---

## 5. Workflows for Common Tasks

### A. Diagnosing the Host Environment
When an AI agent starts a session:
1. Run `wob doctor --json`.
2. Inspect the `checks` array.
3. If any check has `status == "missing"`:
   - Read the `fix` field for that check.
   - Prefer the top-level `quick_fix.command`, which is already resolved for the
     host's package manager (`pkg install -y ...` on Termux,
     `sudo apt install -y openjdk-17-jdk ...` on Debian). Never hard-code
     `pkg install` when `quick_fix.package_manager` is not `termux`.
   - Follow `quick_fix.note` when present: on Termux a stale index needs
     `pkg update` first, and `quick_fix.unavailable` lists tools that no
     distribution packages (Android build-tools, which come from `sdkmanager`).
   - For Android SDK checks, use `wob deps install android-sdk`, which drives
     Google's `sdkmanager`; Termux and Linux distributions do not ship the SDK.
   - Termux packages OpenJDK 17, 21 and 25 (`openjdk-17`, `openjdk-21`,
     `openjdk-25`). There is no `openjdk-11`, and `aapt2` is a separate package
     from `aapt` even though both come from the same build-tools tree.

### B. Creating and Building an Android Application
1. Scaffold project:
   ```bash
   wob create android calculator --package com.example.calculator
   ```
2. Navigate to project:
   ```bash
   cd calculator
   ```
3. Check Android dependencies:
   ```bash
   wob deps doctor
   ```
4. Build APK:
   ```bash
   wob apk build
   ```
5. Inspect the generated APK:
   ```bash
   wob apk info --json
   ```
6. Prompt the user to install on their device:
   ```bash
   wob apk install
   ```
   *Explain that Android will show a system confirmation dialog on their screen.*

### C. Creating and Previewing a Web Application
1. Scaffold project:
   ```bash
   wob create web mydashboard --framework react
   ```
2. Install dependencies:
   ```bash
   cd mydashboard && wob deps install
   ```
3. Launch preview:
   ```bash
   wob web preview
   ```
   *The server binds to `127.0.0.1` by default and prints a Local URL. If the user explicitly asks to test from another device on the same Wi-Fi, run `wob web preview --lan` and report the Network URL (`http://<lan-ip>:3000/`). Explain that this exposes project files to the local network; never enable `--lan` on public Wi-Fi. Dotfiles, `.env`, `.git`, keys, directory listings, traversal paths, and symlink escapes are always blocked.*

---

## 6. Error Handling & Recovery

### Machine-readable failures

Always check the process exit status **and** the JSON body. A failed command never requires scraping a traceback. Expected failures use:

```json
{
  "success": false,
  "error": "Executable not found: 'npm'. Check that it is installed and available in PATH.",
  "error_code": "executable_not_found",
  "hint": "Run 'wob doctor' to identify missing tools and installation commands."
}
```

- `error` is the human-readable cause; show it to the user when appropriate.
- `error_code` is the stable value to branch on in automation. Do not match prose.
- `hint` is a suggested recovery, not proof that recovery succeeded.
- `details`, `warnings`, `errors`, `stdout`, `stderr`, and `returncode` are optional context. Warnings can report successful recovery (for example, a corrupt file backed up before defaults were restored).
- Malformed arguments also honor `--json`, return exit `2`, and include `details.usage`.
- `--verbose` adds traceback/exception diagnostics for debugging; omit it for normal automation.
- If a long-running command already printed a startup JSON document, a later failure document may be written to stderr so stdout remains valid JSON.

`wob self status` exits `1` only when the installation is broken (`--strict` also
fails on warnings). `wob doctor` exits per `--fail-on`/`--strict`, defaulting to
`0` so it stays safe to call from hooks. Every finding in both commands carries a
stable identifier (`runtime.files`, `launcher.present`, `regressions`,
`history.incidents`, …) — assert on those instead of parsing prose.

Common exit statuses: `0` success; `1` operational failure; `2` invalid arguments/config values; `124` timeout; `126` permission-to-execute failure; `127` missing executable; `130` user interrupt. Build/dependency commands may wrap an external failure as exit `1` while retaining the original `returncode` in JSON.

| Error Condition | Likely Cause | Recommended Agent Recovery |
|-----------------|--------------|----------------------------|
| Gradle build fails with OOM / Killed | Android low-memory killer killed java | Check RAM via `wob doctor --json`. Verify `gradle.properties` has `org.gradle.jvmargs=-Xmx1024m` and `--no-daemon`. |
| `termux-open: command not found` | Termux base tools not updated | Propose: `pkg install -y termux-tools` |
| `Cannot execute binary file: Exec format error` | Architecture mismatch | Run `wob doctor --json` to verify machine architecture (`aarch64` vs `arm` vs `x86_64`). |
| Storage permission denied | Android storage not linked | Advise user to run `termux-setup-storage` in their terminal. |
| Port 3000 in use | Another dev server is running | Pass `--port 3001` or let Wobble auto-discover an open port. |
| `wob: installation is damaged` | Installed app files were deleted or modified | The launcher already tried one automatic snapshot restore. If the message persists run `wob self repair --json`; if `wob` cannot start at all, run `wob-rescue` (or `sh ~/.local/share/wobble/rescue.sh`). |
| `wob self verify` reports `modified`/`missing` | Tampering, interrupted write, or partial copy | Run `wob self repair --json`: it restores only the damaged files from the verified snapshot and preserves the originals in `repair-backups/`. Use `--emergency` when the snapshot is gone, or `--accept-current --yes` when the change was intentional. |
| `recovery_source_unavailable` | No snapshot, no source checkout, and downloads were not allowed | Re-run `wob self repair --emergency --from network` (or reinstall with `sh install.sh`). Do not fabricate hashes to silence the check. |
| `wob self status` shows `recovery.snapshot: warning` | The offline safety net is missing or damaged | Run `wob self repair` (rebuilds a missing/damaged snapshot from the now-verified runtime). |
| `wob self status` shows `launcher.present: critical` | Launcher deleted, stale, or pointing at an old app directory | Run `wob self repair` (rewrites only launchers carrying Wobble's marker). |
| `wob self status` shows `installer.leftovers` | An install was interrupted | Run `wob self repair` to remove `.app.tmp-*` / `.app.old`. |
| `wob doctor` reports a regression | A tool disappeared or changed since the last run | Compare the listed check with `previous_run`; re-install the missing package or fix `PATH`. |
| `invalid_project_spec` | `wobble.json` is malformed or has invalid field types | Fix the path in `details.path`; do not run scaffolding over the existing project. |
| `config_write_failed` / `registry_write_failed` | Read-only state, full disk, or insufficient permissions | Check the reported path, free space, and permissions. Retry only after the write can succeed. |
| `invalid_config_value` | Port outside `1..65535` or an unrecognized boolean | Re-run `wob config set` with a valid value; the previous in-memory and on-disk values were preserved. |
| `invalid_apk_archive` | Truncated, corrupted, or non-APK input | Rebuild or re-copy the APK; do not attempt installation of the invalid file. |
| `clean_partial` / `apk_clean_partial` | One or more files could not be deleted | Inspect the per-path `errors` array. Do not assume the workspace is clean; fix permissions and retry. |
| Preview works on the phone but not from a laptop | Localhost-only default | Re-run with `--lan` (trusted networks only) and use the printed `network` URL. |
| User plugin not loading | Unsafe name, writable-by-others directory, or built-in shadowing | Check the `[!]` warning on `wob plugin list`; move it to `~/.wobble/plugins/<safe_name>/plugin.py`, `chmod 700`, and do not reuse built-in names. |

---

## 7. Plugin Authoring Guide

Wobble plugins reside in `wobble/plugins/builtin/<name>/` or `~/.wobble/plugins/<name>/`.

User plugins are treated as untrusted code. To load:
- the directory name must match `^[a-z][a-z0-9_]{1,31}$`;
- the plugin directory and `plugin.py` must not be group- or world-writable (`chmod 700` / `chmod 600`);
- neither may be a symlink;
- the plugin's `name` attribute must be a safe lowercase identifier and must not collide with a built-in (`android`, `nextjs`, `react`, `vue`, `svelte`, `vite`, `python_web`, `php`, `static_web`).

Built-ins are imported by module name in a fixed order (specific frameworks before generic ones), so plugin loading is deterministic. `WOBBLE_ALLOW_UNSAFE_PLUGINS=1` disables the permission checks for development; never set it on shared devices.

Every plugin implements `BasePlugin`:
```python
from pathlib import Path
from wobble.plugins.base import BasePlugin

class CustomPlugin(BasePlugin):
    name = "custom"
    version = "1.0.0"
    description = "Custom framework plugin"
    category = "web"
    required_system_packages = ["git"]
    required_tools = ["git"]

    def detect(self, project_path: Path) -> bool:
        return (project_path / "custom.conf").exists()

    def create_project(self, name: str, target_dir: Path, options=None) -> bool:
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "custom.conf").write_text("# Custom config")
        return True

    def get_dev_command(self, project_path: Path, options=None):
        return ["python3", "-m", "http.server", "3000"]
```

---

## 8. Safety Rules

- Do NOT attempt to install or invoke unverified binary blobs downloaded from random URLs.
- Always use `pkg` (or the host distribution's package manager) and official
  repositories; see `docs/termux_packages.md` for the verified name of every
  package Wobble recommends.
- Keep secrets, tokens, and keystore passwords out of command line arguments and Git commits. `wob apk sign` reads `WOBBLE_KS_PASS` through apksigner's `env:` protocol, so never pass a password as a flag or echo it into logs.
- Do not bind previews or dev servers to `0.0.0.0`/`--lan` on public networks, and never disable the preview server's dotfile/secret blocking.
- Treat `wob self status --deep` (or `wob self verify`) as the source of truth for installation health; let `wob self repair` restore files rather than patching `~/.local/share/wobble/app` by hand. If a patch is intentional, use `wob self repair --accept-current --yes` so the manifest *and* the snapshot record it.
- Never silence a `critical` finding by rewriting hashes. `wob self repair` restores files only from a tree that matches the expected SHA-256 and re-verifies each one afterwards; `--emergency` may download a release archive, so prefer the local snapshot and only opt into the network deliberately.
- Recovery only touches the install root and never the user's projects. Damaged files are preserved under `repair-backups/` (five most recent runs) — read them before deleting anything if the damage needs root-causing.
- Read the incident ledger (`wob self incidents --json`) before debugging intermittent failures; crashes are recorded automatically with the command that triggered them.
- Run `wob --json` commands for machine consumption; the human output is ASCII-styled and intended for terminals.
