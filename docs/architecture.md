# Wobble System Architecture

## 1. High-Level Concept

```
Termux Environment (Android ARM64 / x86_64)
    │
    ▼
Wobble CLI Entrypoint (`bin/wob`)
    │
    ├─► Core Engine
    │     ├── Dynamic Context Detector (`wobble/core/context.py`)
    │     ├── Environment Doctor (`wobble/core/doctor.py`)
    │     ├── Machine Schema (`wobble/core/schema.py`)
    │     ├── Safe Executor (`wobble/core/executor.py`)
    │     └── Structured Logger / JSON Formatter (`wobble/core/logger.py`)
    │
    ├─► Project Management (`wobble/project/`)
    │     ├── Project Spec (`wobble.json`)
    │     ├── Project Registry (`~/.wobble/projects.json`)
    │     └── Scaffolder & Discovery
    │
    ├─► Framework Plugin System (`wobble/plugins/`)
    │     ├── Android Plugin (`plugins/builtin/android`)
    │     ├── Vite Plugin (`plugins/builtin/vite`)
    │     ├── React / Vue / Svelte / Next.js Plugins
    │     ├── Python Web & PHP Plugins
    │     ├── Zero-Dependency Static Web Plugin
    │     └── User Custom Plugins (`~/.wobble/plugins/`)
    │
    ├─► Android & APK Engine (`wobble/android/`)
    │     ├── Gradle Build Coordinator
    │     ├── APK Locator & Finder
    │     ├── Zero-Dependency ZIP/AXML APK Inspector
    │     └── Honest Package Installer (Intent / ADB)
    │
    ├─► Web Engine (`wobble/web/`)
    │     ├── Auto Framework Detector
    │     ├── Dev Server Streamer
    │     └── Localhost & LAN IP Preview Server
    │
    └─► Unified Dependency Manager (`wobble/deps/`)
          ├── Termux Packages (`pkg` / `apt`)
          ├── Node (`npm` / `pnpm` / `yarn`)
          ├── Python (`pip`)
          ├── PHP (`composer`)
          └── Android SDK (`sdkmanager`)
```

## 2. Dynamic Environment Resolution

Wobble never hardcodes paths. On every invocation:
- `$PREFIX` is inspected. If unset, `/data/data/com.termux/files/usr` or `sys.prefix` is resolved.
- `$HOME` is inspected.
- Architecture is detected via `platform.machine()` and normalized (`aarch64`, `arm`, `x86_64`, `x86`).
- Toolchains are discovered dynamically in standard search paths (`$HOME/.local/bin`, `$HOME/bin`, `$PREFIX/bin`, `/system/bin`).
- Android SDK candidates are checked in `$ANDROID_HOME`, `$ANDROID_SDK_ROOT`, `$PREFIX/share/android-sdk`, and `~/android-sdk`.
- Memory (`/proc/meminfo`) and storage (`shutil.disk_usage`) are inspected safely.

## 3. Security Model

- **Zero Root Requirements**: Wobble runs entirely within standard user permissions.
- **W^X Compliance**: All builds and scripts execute from app-private storage.
- **Process Isolation**: Commands run via `subprocess.run` / `Popen` with argument arrays to eliminate shell injection vulnerabilities.
- **Privacy First**: No telemetry, analytics, or outbound background network calls.
