# Wobble (`wob`)

A streamlined, practical development tool for building native Android apps and modern web projects directly inside Termux on Android.

---

## Why Wobble?

If you've ever tried building Android apps or web projects on your phone using Termux, you already know the pain points:

- **Gradle memory crashes:** Standard Gradle spins up background daemons that quickly eat up all your phone's RAM until Android's process killer terminates your build midway.
- **Buried APK outputs:** Compiled APKs end up hidden four folders deep (`app/build/outputs/apk/debug/app-debug.apk`), forcing you to write long copy commands every time you want to test them.
- **Clunky on-device installs:** Non-root Android doesn't let you silently install APKs from the terminal. Most guides assume you have ADB running or root access.
- **Localhost-only web servers:** Default dev servers bind to `127.0.0.1`, which prevents you from testing your work from a laptop or tablet on the same Wi-Fi.

**Wobble** solves these problems with a single CLI tool (`wob`). It gives you project scaffolding, automated Gradle builds tailored for mobile RAM, zero-dependency APK inspection, LAN-ready web previews, and clean on-device APK installation through standard Android intents. No root, no Shizuku, and no desktop machine required.

---

## Quick Start

### 1. Install Wobble

Run the one-line installer in Termux:
```bash
curl -sL https://raw.githubusercontent.com/Rehanasharmin/wobble/main/install.sh | sh
```

Or clone and set it up manually:
```bash
git clone https://github.com/Rehanasharmin/wobble.git ~/wobble
cd ~/wobble
sh install.sh
```

Restart your terminal or run `source ~/.bashrc` so the `wob` command is in your `PATH`.

### 2. Run the Health Check

Before building anything, run the environment doctor:
```bash
wob doctor
```
Wobble checks your CPU architecture (ARM64/x86), RAM, available disk space, Java JDK, Android build tools, Node.js, Python, and Git. If anything is missing, it gives you the exact `pkg install` command to fix it.

---

## Hands-on Workflows

### Native Android Apps

Create and build an Android app right on your phone:

```bash
# 1. Scaffold a new Android project
wob create android myapp --package com.example.myapp

# 2. Enter the directory
cd myapp

# 3. Compile the debug APK
wob apk build
```

Wobble automatically configures Gradle with `--no-daemon` and caps JVM memory at 1024 MB to prevent Android from killing the build process.

Once built, you have three quick ways to work with the APK:

```bash
# Inspect package name, permissions, min/target SDK, and SHA-256
wob apk info

# Trigger the Android system Package Installer dialog directly on your screen
wob apk install

# Export the APK to your phone's Download folder (~/storage/shared/Download)
wob apk share
```

> **Tip:** If `wob apk share` tells you storage isn't set up, run `termux-setup-storage` once in Termux and allow the Android permission prompt.

---

### Modern Web Projects

Wobble supports modern frontend frameworks as well as lightweight Python and PHP backends:

```bash
# Supported frameworks: vite, react, vue, svelte, nextjs, python, php, static
wob create web myfrontend --framework react
cd myfrontend

# Install dependencies (npm, pip, or composer depending on project)
wob deps install

# Start development server
wob web dev
```

#### Preview on Localhost & LAN
Want to test your site on a tablet or laptop connected to the same Wi-Fi? Run:

```bash
wob web preview
```

Wobble starts a preview server and displays both local and network addresses:
```
======================================================
         ⚡ WOBBLE WEB PREVIEW RUNNING
======================================================
  Directory: /data/data/com.termux/files/home/myfrontend
  ➜ Local:    http://localhost:3000/
  ➜ Network:  http://192.168.1.75:3000/
------------------------------------------------------
  Tip: Open the Network URL on any device on your Wi-Fi!
```

The preview server includes built-in SPA fallback routing so client-side routers (React Router, Vue Router, etc.) don't 404 when you refresh a page.

---

## Practical Tips for Developing in Termux

1. **Keep projects in `$HOME`:**  
   Never create projects on `/sdcard` or shared storage. Android's SELinux policy enforces W^X (Write XOR Execute) protections that block running binaries and scripts from shared storage. Always use `~/projects` or `$HOME`.

2. **Low-RAM devices (Under 4 GB):**  
   If Gradle builds fail with out-of-memory errors:
   - Close heavy background apps before compiling.
   - Consider enabling ZRAM / swap if your device kernel supports it.
   - Wobble builds with single-worker execution by default to conserve CPU and RAM.

3. **APK Signing:**  
   Debug APKs are signed automatically by Gradle's debug keystore. If you need to sign a custom or release APK:
   ```bash
   wob apk sign app-release.apk
   ```
   Wobble uses `apksigner` and generates a local keystore if none is provided.

---

## Command Reference

| Command | Description |
|:---|:---|
| `wob doctor` | Run comprehensive system diagnostics and get copy-paste fixes |
| `wob create android <name> [-p pkg]` | Scaffold a native Android Gradle project |
| `wob create web <name> [-f framework]` | Scaffold a web app (`vite`, `react`, `vue`, `svelte`, `nextjs`, `python`, `php`, `static`) |
| `wob project list` | List all discovered and registered projects |
| `wob project info` | Show project stats, file counts, and disk footprint |
| `wob project open <name>` | View quick navigation shortcuts for a project |
| `wob project remove <name>` | Unregister a project from the Wobble index |
| `wob apk build [--release]` | Compile project into an APK with resource-safe Gradle settings |
| `wob apk list` | Locate all generated APKs across the current workspace |
| `wob apk info [file]` | Parse package ID, SDK targets, DEX, permissions, and SHA-256 |
| `wob apk install [file] [--method auto\|termux-open\|am\|adb]` | Launch Android Package Installer prompt on-device |
| `wob apk share [file]` | Copy APK to `~/storage/shared/Download` for easy phone access |
| `wob apk sign [file]` | Sign an APK using `apksigner` |
| `wob apk clean` | Delete generated APKs from build directories |
| `wob web dev [-p port]` | Start framework development server |
| `wob web build` | Build web application for production |
| `wob web test` | Run project test suite |
| `wob web preview [-p port]` | Launch zero-dependency HTTP server with localhost and LAN URLs |
| `wob deps install [stack]` | Install project dependencies or global toolchain stack (`android`, `node`, `python`, `php`) |
| `wob deps add <pkg>` | Add package via detected package manager (`npm`, `pip`, `pkg`, `composer`) |
| `wob deps remove <pkg>` | Remove a package |
| `wob deps doctor` | Check for missing libraries (`node_modules`, `requirements.txt`, JDK) |
| `wob deps list` | View declared project dependencies |
| `wob plugin list` | List installed framework plugins |
| `wob plugin info <name>` | Inspect plugin capabilities and prerequisite status |
| `wob clean [--all]` | Clear build artifacts and caches |
| `wob schema` | Dump machine-readable CLI schema for AI coding agents |

---

## Automation & AI Agents

If you're using Wobble with an automated script or an AI assistant (like Claude, Gemini, or aider running in Termux):

- Pass `--json` to any command to get structured, parseable JSON output instead of colored terminal text.
- Run `wob schema` to retrieve the complete JSON Schema specification of all commands, arguments, and host system metrics.
- See [`AI_GUIDE.md`](AI_GUIDE.md) for agent memory guidelines and toolchain boundaries.

---

## Running the Test Suite

Wobble has a self-contained test suite that verifies argument parsing, scaffolding, framework detection, directory pruning, and APK discovery:

```bash
python3 tests/run_tests.py
```

---

## License

[Apache License 2.0](LICENSE). Free and open-source for the Termux and Android developer community.
