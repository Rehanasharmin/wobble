# Wobble (`wob`)

> **Production-Ready Termux Development Workstation**  
> *"Termux → Wobble → Projects → Frameworks → Build → Test → APK / Web app"*

[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Termux%20%7C%20Android%20ARM64-green.svg)](https://termux.dev)
[![AI Ready](https://img.shields.io/badge/AI%20Agent-Compatible-purple.svg)](AI_GUIDE.md)

**Wobble** turns Termux on Android into a simple, unified, and powerful development workstation. Create, build, test, run, manage, and install Android and modern web applications from one memorable CLI command: `wob`.

Wobble is designed to be **beginner-friendly** for new mobile developers while providing **zero-overhead, machine-readable interfaces (`--json`, `wob schema`)** for experienced developers and AI coding agents.

---

## Quick Start (Up and running in 2 minutes)

### 1. Install Wobble in Termux

Run the one-line installer in Termux:
```bash
curl -sL https://raw.githubusercontent.com/Rehanasharmin/wobble/main/install.sh | sh
```

Or install by cloning the repository:
```bash
git clone https://github.com/Rehanasharmin/wobble.git ~/wobble
cd ~/wobble
sh install.sh
```

### 2. Verify Your Environment
Run the comprehensive environment doctor:
```bash
wob doctor
```
Wobble inspects CPU architecture, storage, RAM, JDK, Gradle, SDK, Node.js, Python, PHP, and gives you actionable copy-paste fixes for anything missing.

### 3. Create Your First Project

#### Native Android App
```bash
# Create an Android project
wob create android myapp --package com.example.myapp

# Navigate and build debug APK
cd myapp
wob apk build

# Inspect APK package, permissions, and size
wob apk info

# Install APK onto your Android phone
wob apk install
```

#### Modern Web Application
```bash
# Create a web application (e.g. Vite, React, Vue, Svelte, or Python)
wob create web mysite --framework react

# Navigate and preview
cd mysite
wob web preview
```
Wobble instantly spins up a local server and outputs:
```
WOBBLE WEB PREVIEW RUNNING
Local:    http://localhost:3000/
Network:  http://192.168.1.45:3000/
```
Open the **Network URL** on any computer, tablet, or phone on your Wi-Fi to test live on real devices!

---

## Key Features

### 1. Unified Project Management
- **Scaffolding:** `wob create android <name>` or `wob create web <name>`.
- **Introspection:** `wob project list`, `wob project info`, and `wob project open <name>`.
- **Machine-readable:** Every project contains a standardized `wobble.json` descriptor.

### 2. Native Android Development on Termux
- **No root required.** Never assumes Shizuku or ADB exists.
- **Toolchain detection:** Detects Java 17/21, Gradle, Android SDK, and native Termux build tools (`aapt`, `apksigner`).
- **Automated builds:** Generates debug and release APKs with resource-conscious Gradle JVM settings (`--no-daemon`, `-Xmx1024m`).
- **Automated APK discovery:** Automatically scans and locates APK outputs.
- **Zero-dependency APK inspector:** Parses APK contents, package IDs, DEX files, ABIs, permissions, and SHA-256 signatures directly in Python without requiring external tools.
- **On-device APK install:** Dispatches Android Package Installer intents cleanly via `termux-open` or `am start`.

### 3. Multi-Technology Web Development
- Supports **Vite, React, Vue, Svelte, Next.js, Python Web (Flask/FastAPI), PHP**, and pure static HTML5/CSS3.
- Framework auto-detection: Wobble automatically detects framework configuration and runs the proper commands.
- Local & LAN previews: Test responsive designs instantly from your laptop or tablet on the same Wi-Fi.

### 4. Unified Dependency Management (`wob deps`)
Clearly routes dependencies to the correct package manager:
- `wob deps install`: Installs project dependencies or toolchain stacks (`android`, `node`, `python`, `php`).
- `wob deps add <pkg>`: Safely adds packages via `termux (pkg)`, `npm`, `pip`, or `composer`.
- `wob deps doctor`: Checks for missing or uninstalled libraries.
- Never silently installs dangerous or unrequested software.

### 5. Environment Doctor (`wob doctor`)
Inspects:
- CPU Architecture (`aarch64`, `arm`, `x86_64`)
- Android OS Release & API level
- Termux version & storage permissions
- Available disk storage and RAM
- Toolchain: Java, Gradle, Android SDK, ADB, Node.js, npm, Python, PHP, Git, build tools
- For every problem, explains what happened and provides a **practical, one-line fix**.

### 6. Modular Framework Plugin System
Extensible architecture where framework support lives in self-contained plugins:
- `plugins/android`
- `plugins/vite`
- `plugins/react`
- `plugins/vue`
- `plugins/svelte`
- `plugins/nextjs`
- `plugins/python_web`
- `plugins/php`
- `plugins/static_web`
- Custom user plugins in `~/.wobble/plugins/` are auto-discovered without touching Wobble core!

### 7. AI Agent Support (`AI_GUIDE.md`)
- `wob schema`: Emits full JSON-Schema specification of all CLI commands, capabilities, and environment metrics.
- `--json`: Every inspection command supports clean, parseable JSON output.
- Comprehensive [AI_GUIDE.md](AI_GUIDE.md) documents safety boundaries, memory rules, and workflows for autonomous coding agents.

---

## Complete CLI Command Reference

| Command | Description |
|---------|-------------|
| `wob doctor` | Run comprehensive environment health diagnostics |
| `wob create android <name>` | Create a new native Android Gradle project |
| `wob create web <name>` | Create a new web project (`--framework vite\|react\|vue\|svelte\|nextjs\|python\|php\|static`) |
| `wob project list` | List all registered and detected projects in workspace |
| `wob project info` | Show metadata, file counts, and size metrics for project |
| `wob project open <name>` | Inspect project and view quick-action commands |
| `wob android build` | Compile Android project into APK with Gradle |
| `wob android clean` | Clean Gradle build caches |
| `wob android limitations` | Honest documentation of Android OS constraints |
| `wob web dev` | Launch framework development server |
| `wob web build` | Build web project for production |
| `wob web test` | Run project test suite |
| `wob web preview` | Launch static preview server with Localhost and LAN IP |
| `wob apk build` | Build APK for current project |
| `wob apk list` | Locate all generated APKs |
| `wob apk info [file]` | Inspect APK details (package, SDKs, DEX, permissions, SHA256) |
| `wob apk install [file]` | Trigger Android package installation |
| `wob apk clean` | Remove generated APK files |
| `wob deps install [stack]` | Install project dependencies or global toolchain |
| `wob deps add <pkg>` | Add dependency (`-m auto\|termux\|npm\|pip\|composer`) |
| `wob deps remove <pkg>` | Remove dependency |
| `wob deps doctor` | Check project dependencies health |
| `wob plugin list` | List active framework plugins |
| `wob plugin info <name>` | Inspect specific framework plugin |
| `wob config list` | Show user configuration settings |
| `wob schema` | Output machine-readable JSON schema for AI agents |

---

## Android OS Reality & Security

Wobble provides an honest development experience:
1. **No Root Claim:** Non-root Android apps cannot silently install APKs in the background. Wobble dispatches a system `ACTION_VIEW` intent via `termux-open`, presenting Android's standard system installation dialog for user confirmation.
2. **Process Memory Constraints:** Android terminates heavy background processes. Wobble configures Gradle with `--no-daemon` and `-Xmx1024m` to prevent OOM termination.
3. **W^X Protection:** All code and toolchains reside strictly within Termux private data storage (`$PREFIX` and `$HOME`).
4. **Dynamic Paths:** Never hardcodes `/data/data/...` paths; detects `$PREFIX` and environment variables dynamically for compatibility across Android ROMs and forks.

---

## Testing

Wobble includes an automated test suite verifying CLI parsing, project scaffolding, framework detection, APK discovery, JSON outputs, and Termux compatibility:

```bash
python3 tests/run_tests.py
```

---

## License

Apache License 2.0. Open source and free for the Termux and Android development community.
