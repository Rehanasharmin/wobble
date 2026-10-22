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
  "wobble_version": "1.2.0",
  "created_at": "2026-10-03T05:40:00Z",
  "package_id": "com.example.myapp",
  "scripts": {
    "build": "wob android build",
    "clean": "wob android clean",
    "apk": "wob apk info",
    "install": "wob apk install"
  },
  "dependencies": {
    "system": ["openjdk-17"],
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
| Check System Health | `wob doctor` | `wob doctor --json` | Returns status, storage, missing tools, and exact fixes |
| Fast Health Check | `wob doctor --quick` | `wob doctor --json --quick` | Skips subprocess version probes (~2.5× faster) |
| Check Installation | `wob self status` | `wob self status --json` | Reports standalone vs source-checkout mode and source independence |
| Verify Installation | `wob self verify` | `wob self verify --json` | Re-hashes installed files; `ok=false` plus `missing`/`modified` on damage |
| List Projects | `wob project list` | `wob project list --json` | Lists registered and scanned projects |
| Project Info | `wob project info` | `wob project info --json` | Returns file metrics and configuration |
| Create Android Project | `wob create android <name>` | `wob create android <name> --package <pkg>` | Scaffolds build.gradle, Java, Layout, Manifest |
| Create Web Project | `wob create web <name>` | `wob create web <name> --framework <fw>` | Frameworks: `vite`, `react`, `vue`, `svelte`, `nextjs`, `python`, `php`, `static` |
| Build APK | `wob apk build` | `wob apk build --json` | Executes Gradle build and locates APK |
| List APKs | `wob apk list` | `wob apk list --json` | Finds all APK files in build outputs |
| Inspect APK | `wob apk info <file>` | `wob apk info <file> --json` | Returns package, SDKs, DEX, SHA256, permissions |
| Install APK | `wob apk install <file>` | `wob apk install <file> --json` | Dispatches Android package installer intent |
| Install Dependencies | `wob deps install` | `wob deps install <stack>` | Stacks: `android`, `node`, `python`, `php` |
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
   - Read the `fix` field.
   - For missing Termux tools, propose installing the recommended packages (e.g. `pkg install -y openjdk-17 nodejs git`).

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

| Error Condition | Likely Cause | Recommended Agent Recovery |
|-----------------|--------------|----------------------------|
| Gradle build fails with OOM / Killed | Android low-memory killer killed java | Check RAM via `wob doctor --json`. Verify `gradle.properties` has `org.gradle.jvmargs=-Xmx1024m` and `--no-daemon`. |
| `termux-open: command not found` | Termux base tools not updated | Propose: `pkg install -y termux-tools` |
| `Cannot execute binary file: Exec format error` | Architecture mismatch | Run `wob doctor --json` to verify machine architecture (`aarch64` vs `arm` vs `x86_64`). |
| Storage permission denied | Android storage not linked | Advise user to run `termux-setup-storage` in their terminal. |
| Port 3000 in use | Another dev server is running | Pass `--port 3001` or let Wobble auto-discover an open port. |
| `wob: installation is damaged` | Installed app files were deleted or modified | Run `wob self verify --json`; reinstall with `sh install.sh` or `wob self install`. |
| `wob self verify` reports `modified`/`missing` | Tampering, interrupted write, or partial copy | Reinstall with `sh install.sh`; do not rely on the damaged runtime. |
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
- Always use `pkg` or official Termux package repositories.
- Keep secrets, tokens, and keystore passwords out of command line arguments and Git commits. `wob apk sign` reads `WOBBLE_KS_PASS` through apksigner's `env:` protocol, so never pass a password as a flag or echo it into logs.
- Do not bind previews or dev servers to `0.0.0.0`/`--lan` on public networks, and never disable the preview server's dotfile/secret blocking.
- Treat `wob self verify` as the source of truth for installation health; reinstall rather than patching files inside `~/.local/share/wobble/app` by hand.
- Run `wob --json` commands for machine consumption; the human output is ASCII-styled and intended for terminals.
