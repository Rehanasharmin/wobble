# Wobble (`wob`)

**Wobble** is a free and open-source command-line development harness for building native Android applications and modern web projects directly inside [Termux](https://termux.dev) on Android devices.[1] Written in Python 3 with a single entry-point command (`wob`), it provides project scaffolding, resource-aware Gradle builds, zero-dependency APK inspection, on-device APK installation, LAN-ready web previews, and unified dependency management — without requiring root access, Shizuku, or a desktop computer.

Wobble is designed around the constraints of mobile hardware and the Android security model: it disables the memory-hungry Gradle daemon by default,[5] never executes binaries from shared storage (which Android mounts with the `noexec` flag),[3][4] and installs compiled APKs through the standard Android package-installer intent rather than privileged APIs.[6]

---

## Quick facts

| | |
|:---|:---|
| **Original author** | Rehan Ashar Min and [contributors](https://github.com/Rehanasharmin/wobble/graphs/contributors) |
| **Initial release** | 3 October 2026 |
| **Stable release** | 1.1.0 (17 October 2026) |
| **Written in** | Python 3, POSIX shell |
| **Platform** | Termux on Android; mainstream Linux distributions |
| **Type** | Command-line development harness, build tool, project scaffold |
| **License** | [Apache License 2.0](LICENSE) |
| **Repository** | [github.com/Rehanasharmin/wobble](https://github.com/Rehanasharmin/wobble) |
| **Command name** | `wob` |
| **Root required** | No |
| **Size** | ~220 KB of source; no third-party Python dependencies |

---

## Contents

1. [Overview](#overview)
2. [Background](#background)
3. [History](#history)
4. [Features](#features)
5. [Design and architecture](#design-and-architecture)
6. [Installation](#installation)
7. [Workflows](#workflows)
8. [Command reference](#command-reference)
9. [Performance](#performance)
10. [Stability and data safety](#stability-and-data-safety)
11. [Limitations](#limitations)
12. [Automation and AI agents](#automation-and-ai-agents)
13. [Development and testing](#development-and-testing)
14. [References](#references)
15. [External links](#external-links)
16. [License](#license)

---

## Overview

Wobble addresses the practical difficulties of compiling software on a phone. Standard Android development tooling assumes a desktop workstation: Gradle's default daemon keeps a multi-hundred-megabyte JVM resident in memory,[5] compiled APKs are buried several directories deep inside `app/build/outputs/`, development servers bind to `127.0.0.1` (unreachable from other devices), and Android's security policy forbids silently installing APKs without user confirmation.[6]

Wobble wraps these workflows in one discoverable CLI. A typical session looks like:

```bash
wob doctor                     # diagnose the environment and print copy-paste fixes
wob create android myapp       # scaffold a Gradle project tuned for mobile RAM
cd myapp
wob apk build                  # compile a debug APK with a memory-capped JVM
wob apk info                   # inspect package ID, SDK targets, permissions, SHA-256
wob apk install                # hand the APK to the Android package installer
```

Every command supports `--json` for machine-readable output, `--no-color` for plain terminals, and `wob schema` publishes a complete JSON specification of the tool for automation.

---

## Background

Developing software on Android devices involves several platform-level constraints that Wobble is designed to work within rather than bypass:

- **Binary execution policy.** Since Android 10, untrusted applications that target API level 29 or higher may not invoke `exec()` on files inside the app's writable home directory; Google describes this as a W^X (write xor execute) violation, and apps may load binary code only from inside their APK.[3] Termux consequently keeps its toolchain inside its private data directory and discourages running binaries from shared storage, which is additionally mounted with the `noexec` flag.[4] Wobble follows the same rule: projects live in `$HOME`, and `wob doctor` warns when a workspace sits on shared storage.

- **Packaging and distribution policy.** Google Play's target-API requirements broke Termux updates on the Play Store channel starting in 2020; the Termux maintainers designate F-Droid and GitHub releases as the only official installation sources and keep Play Store builds deprecated.[1][2] Wobble's own installer is therefore channel-agnostic: a one-line script or a plain `git clone`.

- **Memory pressure.** The Gradle daemon is enabled by default and retains a JVM heap between builds (512 MB–1 GB by default).[5] On devices with 3–6 GB of total RAM — much of it consumed by Android itself — a lingering daemon routinely triggers the low-memory killer mid-build. Wobble-generated projects set `org.gradle.daemon=false`, cap the JVM heap at 1024 MB (`-Xmx1024m`), and disable parallel workers.

- **No privileged install path.** Android requires that package installation be confirmed by the user through the system package installer; the supported programmatic route is an `ACTION_VIEW` intent carrying the MIME type `application/vnd.android.package-archive`.[6] Wobble dispatches exactly this intent (via `termux-open`, `termux-am`, or `adb`) and reports honestly whether the intent was sent — it never claims a silent install succeeded.

---

## History

Wobble was created by Rehan Ashar Min in October 2026 to consolidate ad-hoc Termux build scripts into a single maintainable tool. The first commit (`ef3b5f4`, 3 October 2026) introduced the plugin-based architecture, the `wob` dispatcher, Android and web project scaffolds, the environment doctor, and the self-contained test suite.

Version 1.1.0 (17 October 2026) focused on user experience, performance, and stability: command startup was made lazy so trivial commands avoid importing heavyweight modules, environment diagnostics began probing tools concurrently, the web preview server became multi-threaded, configuration and registry files started being written atomically with corruption recovery, shell completion was added, and typo suggestions were introduced across framework, plugin, and configuration names.

---

## Features

| Area | Capability |
|:---|:---|
| **Environment doctor** | `wob doctor` audits CPU architecture, Android version, RAM, disk space, Java/Gradle/SDK, Node.js, Python, PHP, Git, and ADB; every failed check ships with a copy-paste `pkg install` fix. Tool version probes run concurrently. |
| **Android projects** | `wob create android` scaffolds a complete Gradle project (`build.gradle`, `settings.gradle`, `gradle.properties`, manifest, activity, resources) with memory-safe defaults: daemon disabled, `-Xmx1024m` heap, single-worker builds. |
| **APK tooling** | Locate build outputs automatically; inspect package name, version, min/target SDK, permissions, native ABIs, DEX entries, and SHA-256 using `aapt`/`aapt2` when present or a pure-Python binary-XML fallback when not. Sign with `apksigner`; export to the Android Download folder. |
| **On-device installation** | `wob apk install` opens the system package installer through `termux-open`, `termux-am`, or `adb`, with `--method` to force a specific transport. |
| **Web projects** | Scaffolds Vite, React, Vue, Svelte, Next.js, Python, PHP, and static sites. `wob web dev` runs the framework dev server bound to `0.0.0.0`; `wob web preview` serves a zero-dependency static server with SPA history fallback. |
| **LAN preview** | Preview and dev servers print both `localhost` and LAN URLs (detected at runtime), enabling cross-device testing from a laptop or tablet on the same Wi-Fi network. |
| **Dependency management** | `wob deps install / add / remove / doctor / list` drives `pkg`, `npm`, `pnpm`, `yarn`, `pip`, and `composer` after auto-detecting the project type from lockfiles and manifests. |
| **Plugin system** | Frameworks are discovered as plugins under `wobble/plugins/builtin/` and user plugins under `~/.wobble/plugins/`, with alias resolution (`python` → `python_web`, `static` → `static_web`, …). |
| **Shell completion** | `wob completion bash` / `wob completion zsh` emit completion scripts covering commands, subcommands, and common flags. |
| **Machine-readable output** | `--json` on every command; `wob schema` emits the full command/argument/capability specification for AI coding agents and scripts. |
| **Project registry** | `wob project list / info / open / remove` indexes projects in `~/.wobble/projects.json`, pruning stale entries automatically. |

---

## Design and architecture

Wobble is organized as a set of small, single-purpose Python packages. Subcommand modules are imported lazily, so `wob --version` or `wob config get` never pay for the HTTP server, APK parser, or plugin loader.

| Module | Responsibility |
|:---|:---|
| `wobble/cli.py` | Argument parsing and command dispatch; friendly errors and exit codes |
| `wobble/core/context.py` | Runtime detection: Termux, architecture, RAM, storage, Android properties, LAN IP |
| `wobble/core/executor.py` | Safe subprocess execution with timeouts, environment injection, and streaming |
| `wobble/core/doctor.py` | Parallelized environment diagnostics with actionable fixes |
| `wobble/core/config.py` | Persistent settings in `~/.config/wobble/config.json` with corruption recovery |
| `wobble/core/fsutil.py` | Atomic file writes (temp file + rename) for crash-safe persistence |
| `wobble/core/schema.py` | JSON schema of every command for AI agents |
| `wobble/plugins/` | `BasePlugin` contract plus built-in framework plugins (Vite, React, Vue, Svelte, Next.js, Python, PHP, static, Android) |
| `wobble/android/` | Gradle build coordination, APK inspection/install/sign/share, SDK detection, honest limitation reporting |
| `wobble/web/` | Framework detection, dev/build/test runners, threaded static preview server |
| `wobble/project/` | `wobble.json` project specs, discovery, registry, metrics |
| `wobble/deps/` | Unified `pkg`/`npm`/`pip`/`composer` dependency operations |

The plugin contract (`wobble/plugins/base.py`) defines `detect`, `create_project`, and `get_dev_command` / `get_build_command` / `get_test_command` / `get_clean_command` hooks, so additional frameworks can be supported without touching the core.

---

## Installation

### One-line install (Termux)

```bash
curl -sL https://raw.githubusercontent.com/Rehanasharmin/wobble/main/install.sh | sh
```

### Manual install

```bash
git clone https://github.com/Rehanasharmin/wobble.git ~/wobble
cd ~/wobble
sh install.sh
```

Restart the terminal or run `source ~/.bashrc` so `wob` is on your `PATH`, then verify the environment:

```bash
wob doctor
```

> **Note:** Install Termux from [F-Droid](https://f-droid.org/packages/com.termux/) or [GitHub Releases](https://github.com/termux/termux-app/releases) — the Google Play builds are deprecated and no longer receive updates.[1][2]

---

## Workflows

### Native Android apps

```bash
wob create android myapp --package com.example.myapp
cd myapp
wob apk build              # debug build (add --release for release)
wob apk info               # package, SDK levels, permissions, SHA-256
wob apk install            # open the Android package installer prompt
wob apk share              # copy the APK to ~/storage/shared/Download
```

Generated projects pin Gradle to `--no-daemon` with `org.gradle.jvmargs=-Xmx1024m` and `org.gradle.parallel=false`, which trades peak build speed for reliable completion on memory-constrained devices.[5]

### Modern web projects

```bash
# frameworks: vite, react, vue, svelte, nextjs, python, php, static
wob create web myfrontend --framework react
cd myfrontend
wob deps install           # npm/pip/composer auto-detected
wob web dev                # framework dev server on 0.0.0.0
wob web preview            # zero-dependency static server + SPA fallback
```

`wob web preview` prints both local and network addresses for cross-device testing:

```
======================================================
         ⚡ WOBBLE WEB PREVIEW RUNNING
======================================================
  Directory: /data/data/com.termux/files/home/myfrontend
  ➜ Local:    http://localhost:3000/
  ➜ Network:  http://192.168.1.75:3000/
------------------------------------------------------
```

The preview server handles requests concurrently and falls back to `index.html` for client-side routes so routers such as React Router survive a page refresh.

---

## Command reference

| Command | Description |
|:---|:---|
| `wob doctor` | Run system diagnostics and get copy-paste fixes |
| `wob create android <name> [-p pkg]` | Scaffold a native Android Gradle project |
| `wob create web <name> [-f framework]` | Scaffold a web app (`vite`, `react`, `vue`, `svelte`, `nextjs`, `python`, `php`, `static`) |
| `wob project list / info / open / remove` | Manage the project registry |
| `wob android build / clean / info / limitations` | Native Android workflows and constraint report |
| `wob apk build [--release]` | Compile the project into an APK |
| `wob apk list / info [file]` | Locate and parse APK metadata |
| `wob apk install [file] [--method auto\|termux-open\|am\|adb]` | Open the Android package installer |
| `wob apk share [file] [--dest dir]` | Export the APK to shared Download storage |
| `wob apk sign [file] [--keystore ks] [--alias a]` | Sign an APK with `apksigner` |
| `wob apk clean` | Delete generated APKs |
| `wob web dev [-p port] [--host h]` | Start the framework development server |
| `wob web build / test` | Production build / test suite |
| `wob web preview [-p port] [--dir d]` | Threaded static preview with SPA fallback and LAN URLs |
| `wob web serve [-p port]` | Static HTTP file server |
| `wob deps install [stack] / add / remove / doctor / list` | Unified dependency management (`pkg`, `npm`, `pip`, `composer`) |
| `wob plugin list / info <name>` | Inspect framework plugins and prerequisites |
| `wob config list / get / set` | Persistent user configuration |
| `wob clean [--all] [-y]` | Remove build artifacts and caches (`--all` adds `node_modules`, Gradle caches; prompts first) |
| `wob completion [bash\|zsh]` | Generate a shell completion script |
| `wob build / dev / preview` | Project-type-aware shortcuts |
| `wob update` | Check the installed version |
| `wob schema` | Dump the machine-readable CLI schema |

Global flags: `--json`, `--no-color`, `--verbose`, `--version`.

---

## Performance

Wobble applies several deliberate optimizations for mobile hardware:

- **Lazy command dispatch.** Subcommand modules are imported only when invoked; trivial commands (`--version`, `config get`, `completion`) avoid loading the HTTP stack, APK parser, and plugin registry entirely.
- **Concurrent diagnostics.** `wob doctor` probes tool versions in parallel (each probe is a subprocess), which removes most of the wall-clock cost of sequential spawning.
- **Memoized detection.** Android system properties (`getprop` subprocess calls) and the LAN IP (routing-table socket probe) are computed once per process.
- **Threaded preview server.** The built-in preview serves each request on its own daemon thread, so one slow or stalled client cannot block others on the LAN.
- **Pruned file walks.** APK discovery and project metrics skip `.git`, `node_modules`, `.gradle`, `.venv`, and similar heavy directories.
- **Memory-safe Gradle defaults.** Builds run with `--no-daemon`, `-Xmx1024m`, and parallel workers disabled to survive Android's low-memory killer.[5]

---

## Stability and data safety

- **Atomic writes.** Configuration, the project registry, and `wobble.json` specs are written to a temporary file and renamed into place, so an interrupted write cannot truncate them.
- **Corruption recovery.** An unreadable `config.json` is preserved as `config.json.corrupt.bak` before defaults are restored — user data is never silently destroyed.
- **Timeouts on all subprocesses.** External tools run with bounded timeouts and are killed cleanly on interrupt; a failed or missing executable produces a clear error (exit 127) rather than a traceback.
- **Graceful interrupts.** `Ctrl+C` terminates child processes, exits with status 130, and never leaves detached Gradle or dev-server processes behind.
- **Defensive registry handling.** Stale project entries are pruned in a single batched write; malformed registry entries are ignored instead of crashing the tool.
- **Full test coverage.** 81 automated tests verify parsing, scaffolding, detection, executor behavior, doctor reporting, JSON output, and the safety properties above.

---

## Limitations

Wobble reports its constraints honestly via `wob android limitations`:

- **No silent installs.** Android requires user confirmation for package installation; Wobble dispatches the system installer intent and cannot bypass the prompt.[6]
- **No root-only features.** Operations that require superuser (modifying `/system`, silent installs via privileged APIs) are out of scope.
- **Shared storage is not executable.** Android mounts shared storage with `noexec`; projects must live in `$HOME` (typically `~/projects`), never on `/sdcard`.[3][4]
- **Gradle on low RAM.** Large multi-module projects can still exhaust memory even with capped heap; closing background apps or enabling ZRAM/swap helps.
- **Termux distribution channel matters.** Play Store builds of Termux are deprecated; building against them is unsupported.[1][2]

---

## Automation and AI agents

Wobble is designed to be driven by scripts and coding agents:

```bash
wob --json doctor          # structured environment report
wob --json project list    # parseable project inventory
wob schema                 # complete JSON schema of commands and host metrics
```

Conventions for agents (`AI_GUIDE.md`):

1. Always consume `--json` output instead of scraping ANSI text.
2. Never assume root, ADB, or Shizuku are present — confirm with `wob doctor --json`.
3. Respect the W^X constraint: keep code and binaries in `$HOME`.[3][4]
4. Prefer `wob apk install` over manual `pm` invocations for on-device installs.

---

## Development and testing

```bash
git clone https://github.com/Rehanasharmin/wobble.git
cd wobble
python3 tests/run_tests.py
```

The test suite is dependency-free (standard-library `unittest` only) and runs in under a second. Project layout, plugin authoring, and platform-specific notes are documented in [`docs/`](docs/) — see [`docs/architecture.md`](docs/architecture.md), [`docs/plugins.md`](docs/plugins.md), [`docs/android_guide.md`](docs/android_guide.md), and [`docs/web_guide.md`](docs/web_guide.md). Contributions follow [`CONTRIBUTING.md`](CONTRIBUTING.md).

---

## References

1. Termux project. "Termux — a terminal emulator application for Android OS." *termux.dev* / [termux/termux-app](https://github.com/termux/termux-app). Retrieved 17 October 2026.
2. Termux maintainers. "Response Regarding Google PlayStore App Updates." *termux/termux-app Discussion #4000*, 8 June 2024 — Play Store releases remain deprecated; F-Droid and GitHub are the only official release sources. [github.com/termux/termux-app/discussions/4000](https://github.com/termux/termux-app/discussions/4000)
3. Android Open Source Project. "Behavior changes: all apps — Execute permission (Android 10)." *developer.android.com* — untrusted apps targeting API 29 cannot `exec()` files in the app home directory (W^X). [developer.android.com/about/versions/10/behavior-changes-all#execute-permission](https://developer.android.com/about/versions/10/behavior-changes-all#execute-permission)
4. Termux developers. "Termux execution environment." *termux/termux-packages Wiki* — external/shared storage is mounted `noexec`; files cannot be executed directly from `/sdcard`. [github.com/termux/termux-packages/wiki/Termux-execution-environment](https://github.com/termux/termux-packages/wiki/Termux-execution-environment)
5. Gradle. "The Gradle Daemon." *Gradle User Manual* — daemon enabled by default; `--no-daemon` disables it; default daemon heap 512 MB–1 GB. [docs.gradle.org/current/userguide/gradle_daemon.html](https://docs.gradle.org/current/userguide/gradle_daemon.html)
6. Android Open Source Project. "Common intents — Install an app." *developer.android.com* — package installation is performed through an `ACTION_VIEW` intent with MIME type `application/vnd.android.package-archive`. [developer.android.com/guide/components/intents-filters](https://developer.android.com/guide/components/intents-filters)
7. Vite. "Server options." *Vite documentation* — `server.host` controls dev-server bind address (`0.0.0.0` exposes on the LAN). [vitejs.dev/config/server-options.html](https://vitejs.dev/config/server-options.html)
8. The Apache Software Foundation. "Apache License, Version 2.0." 2004. [apache.org/licenses/LICENSE-2.0](https://www.apache.org/licenses/LICENSE-2.0)
9. F-Droid. "Termux." *F-Droid package repository*. [f-droid.org/packages/com.termux/](https://f-droid.org/packages/com.termux/)

---

## External links

- [Wobble source repository](https://github.com/Rehanasharmin/wobble)
- [Termux](https://termux.dev)
- [Termux on F-Droid](https://f-droid.org/packages/com.termux/)
- [Android Developers](https://developer.android.com)
- [Gradle User Manual](https://docs.gradle.org/current/userguide/userguide.html)
- [Vite Documentation](https://vitejs.dev)

---

## License

Wobble is released under the [Apache License 2.0](LICENSE) — free and open-source software for the Termux and Android developer community.
