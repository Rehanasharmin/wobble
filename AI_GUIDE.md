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
  "wobble_version": "1.0.0",
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
| Start Web Dev Server | `wob web dev` | `wob web dev --port 3000` | Streams dev server output |
| Web Preview (Local & LAN) | `wob web preview` | `wob web preview --port 3000` | Starts zero-dependency server, provides LAN IP |

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
   *The agent can report the Local (`http://localhost:3000/`) and Network LAN URL (`http://<lan-ip>:3000/`) so the user can open it on their mobile browser or another device.*

---

## 6. Error Handling & Recovery

| Error Condition | Likely Cause | Recommended Agent Recovery |
|-----------------|--------------|----------------------------|
| Gradle build fails with OOM / Killed | Android low-memory killer killed java | Check RAM via `wob doctor --json`. Verify `gradle.properties` has `org.gradle.jvmargs=-Xmx1024m` and `--no-daemon`. |
| `termux-open: command not found` | Termux base tools not updated | Propose: `pkg install -y termux-tools` |
| `Cannot execute binary file: Exec format error` | Architecture mismatch | Run `wob doctor --json` to verify machine architecture (`aarch64` vs `arm` vs `x86_64`). |
| Storage permission denied | Android storage not linked | Advise user to run `termux-setup-storage` in their terminal. |
| Port 3000 in use | Another dev server is running | Pass `--port 3001` or let Wobble auto-discover an open port. |

---

## 7. Plugin Authoring Guide

Wobble plugins reside in `wobble/plugins/builtin/<name>/` or `~/.wobble/plugins/<name>/`.

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
- Keep secrets, tokens, and keystore passwords out of command line arguments and Git commits.
