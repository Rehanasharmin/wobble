# Wobble (`wob`)

**Wobble** is a free and open-source command-line development harness for building native Android applications and modern web projects directly inside [Termux](https://termux.dev) on Android devices.[1] Written in Python 3 with a single entry-point command (`wob`), it provides project scaffolding, resource-aware Gradle builds, zero-dependency APK inspection, on-device APK installation, LAN-ready web previews, and unified dependency management — without requiring root access, Shizuku, or a desktop computer. Also you can visit our website [Wobble CLI](https://wobble-cli.netlify.app/).

Wobble is designed around the constraints of mobile hardware and the Android security model: it disables the memory-hungry Gradle daemon by default,[5] never executes binaries from shared storage (which Android mounts with the `noexec` flag),[3][4] and installs compiled APKs through the standard Android package-installer intent rather than privileged APIs.[6]

Starting with version 1.2.0, Wobble installs like ordinary software rather than as a symlink into a Git checkout: the runtime is copied into `~/.local/share/wobble/app`, bytecode is precompiled, and the generated launcher keeps working even if the checkout is deleted. The interface uses a pure-ASCII wordmark and status badges throughout, and the preview server is hardened against secret-file disclosure, directory listings, and symlink escapes.

---

## Quick facts

| | |
|:---|:---|
| **Original author** | Rehan Ashar Min and [contributors](https://github.com/Rehanasharmin/wobble/graphs/contributors) |
| **Initial release** | 3 October 2026 |
| **Stable release** | 1.2.0 (21 October 2026) |
| **Written in** | Python 3, POSIX shell |
| **Platform** | Termux on Android; mainstream Linux distributions |
| **Type** | Command-line development harness, build tool, project scaffold |
| **License** | [Apache License 2.0](LICENSE) |
| **Repository** | [github.com/Rehanasharmin/wobble](https://github.com/Rehanasharmin/wobble) |
| **Command name** | `wob` |
| **Root required** | No |
| **Size** | ~1 MB installed (≈350 KB source + precompiled bytecode); no third-party Python dependencies |

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

Wobble addresses the practical difficulties of compiling software on a phone. Standard Android development tooling assumes a desktop workstation: Gradle's default daemon keeps a multi-hundred-megabyte JVM resident in memory,[5] compiled APKs are buried several directories deep inside `app/build/outputs/`, development servers default to `127.0.0.1` (unreachable from other devices) without an obvious safe way to opt into LAN testing, and Android's security policy forbids silently installing APKs without user confirmation.[6]

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

Version 1.2.0 (21 October 2026) replaced the source-dependent symlink installer with a standalone application installer (copy + manifest + precompiled bytecode + generated launcher), added `wob self status/verify/install/uninstall`, a `--version` fast path that bypasses argument parsing, memoized environment probes, a dependency-free ASCII theme (wordmark, rules, boxes, badges, meters), hardened preview defaults (localhost-only, dotfile/secret blocking, no directory listings, symlink-escape prevention), gzip-compressed preview responses, strict project-name/package validation, trust checks for user plugins, environment-variable keystore passwords, and global flags that work on either side of the subcommand.

---

## Features

| Area | Capability |
|:---|:---|
| **Environment doctor** | `wob doctor` audits CPU architecture, Android version, RAM, disk space, Java/Gradle/SDK, Node.js, Python, PHP, Git, and ADB; every failed check ships with a copy-paste `pkg install` fix. Tool version probes run concurrently. |
| **Android projects** | `wob create android` scaffolds a complete Gradle project (`build.gradle`, `settings.gradle`, `gradle.properties`, manifest, activity, resources) with memory-safe defaults: daemon disabled, `-Xmx1024m` heap, single-worker builds. |
| **APK tooling** | Locate build outputs automatically; inspect package name, version, min/target SDK, permissions, native ABIs, DEX entries, and SHA-256 using `aapt`/`aapt2` when present or a pure-Python binary-XML fallback when not. Sign with `apksigner`; export to the Android Download folder. |
| **On-device installation** | `wob apk install` opens the system package installer through `termux-open`, `termux-am`, or `adb`, with `--method` to force a specific transport. |
| **Standalone install** | `sh install.sh` copies the runtime into `~/.local/share/wobble/app`, writes a manifest with SHA-256 hashes, precompiles bytecode, generates a self-contained `~/.local/bin/wob` launcher, installs bash/zsh completions, and optionally updates `PATH`. The source checkout can be deleted afterwards. |
| **Self-management** | `wob self status` shows install mode and source independence; `wob self verify` re-hashes every installed file; `wob self uninstall` (or `sh uninstall.sh`) removes Wobble while preserving projects and, unless `--purge` is passed, config. |
| **Web projects** | Scaffolds Vite, React, Vue, Svelte, Next.js, Python, PHP, and static sites. Dev servers bind to localhost by default; `--lan` exposes them on the local network. `wob web preview` serves a zero-dependency static server with SPA history fallback. |
| **Hardened preview** | Dotfiles (`.git`, `.env`), credential files (`*.pem`, `*.jks`, `id_rsa`, `local.properties`), directory listings, path traversal, and symlink escapes are blocked. Responses are gzip-compressed with a small in-memory cache and HTTP/1.1 keep-alive. |
| **LAN preview** | `wob preview --lan` prints the local and LAN URLs and shows an explicit Wi-Fi exposure warning, enabling cross-device testing without silently exposing project sources on public networks. |
| **Dependency management** | `wob deps install / add / remove / doctor / list` drives `pkg`, `npm`, `pnpm`, `yarn`, `pip`, and `composer` after auto-detecting the project type from lockfiles and manifests. |
| **Plugin system** | Frameworks are discovered as plugins under `wobble/plugins/builtin/` and user plugins under `~/.wobble/plugins/`, with alias resolution (`python` → `python_web`, `static` → `static_web`, …). Built-ins are imported by module name (fast and deterministic); user plugins must live in a private, non-world-writable directory and can never shadow a built-in. |
| **ASCII interface** | Pure-ASCII wordmark, section rules, boxes, `[ OK ] / [WARN] / [MISS] / [FAIL]` badges, and `[####>-----]` meters. Colour is opt-out via `--no-color` or `NO_COLOR`; JSON output is never decorated. |
| **Shell completion** | `wob completion bash` / `wob completion zsh` emit completion scripts covering commands, subcommands, and common flags; the installer places them in the standard completion directories. |
| **Machine-readable output** | `--json` on every command; failures include `success: false`, a stable `error_code`, an actionable message, and optional `hint`/`details`. Child-process output is captured so it cannot corrupt JSON. `wob schema` publishes the full contract. |
| **Project registry** | `wob project list / info / open / remove` indexes projects in `~/.wobble/projects.json`, pruning stale entries automatically. |

---

## Design and architecture

Wobble is organized as a set of small, single-purpose Python packages. Subcommand modules are imported lazily, so `wob --version` or `wob config get` never pay for the HTTP server, APK parser, or plugin loader.

| Module | Responsibility |
|:---|:---|
| `wobble/bootstrap.py` | Fast path for `--version` and the bare-command landing screen; shared by the launcher and `python -m wobble` |
| `wobble/cli.py` | Argument parsing and command dispatch; friendly errors and exit codes |
| `wobble/core/errors.py` | Shared expected-error types, recovery hints, exit codes, and JSON failure payloads |
| `wobble/core/installer.py` | Standalone install/uninstall/verify/status: manifest, hashes, bytecode compilation, launcher generation |
| `wobble/core/theme.py` | Dependency-free ASCII theme: banner, rules, boxes, badges, meters, colour detection |
| `wobble/core/completions.py` | Bash and zsh completion scripts shared by `wob completion` and the installer |
| `wobble/core/context.py` | Runtime detection: Termux, architecture, RAM, storage, Android properties, LAN IP |
| `wobble/core/executor.py` | Safe subprocess execution with timeouts, environment injection, and streaming |
| `wobble/core/doctor.py` | Parallelized environment diagnostics with actionable fixes |
| `wobble/core/config.py` | Persistent settings in `~/.config/wobble/config.json` with corruption recovery |
| `wobble/core/fsutil.py` | Atomic file writes (temp file + rename) for crash-safe persistence |
| `wobble/core/schema.py` | JSON schema of every command for AI agents |
| `wobble/plugins/` | `BasePlugin` contract plus built-in framework plugins (Vite, React, Vue, Svelte, Next.js, Python, PHP, static, Android) |
| `wobble/android/` | Gradle build coordination, APK inspection/install/sign/share, SDK detection, honest limitation reporting |
| `wobble/web/` | Framework detection, dev/build/test runners, hardened threaded static preview server (gzip, keep-alive, secret-file blocking) |
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

### What the installer actually does

The old workflow symlinked `~/.local/bin/wob` into the checkout, so deleting the checkout broke the command. Wobble 1.2.0 installs like a normal application:

1. Copies the `wobble` package, license, and docs into `~/.local/share/wobble/app`.
2. Precompiles every module to `__pycache__` for faster first runs.
3. Writes `~/.local/share/wobble/install.json` with the version, source path, launcher paths, and a SHA-256 hash for every installed file.
4. Generates `~/.local/bin/wob` — a standalone POSIX-shell launcher containing the absolute app path. It never references the source checkout.
5. Installs bash/zsh completion files under `~/.local/share/`.
6. Appends an idempotent `# >>> wobble >>>` PATH block to `~/.bashrc`, `~/.zshrc`, or `~/.profile` (skip with `--no-path`).

```
~/.local/share/wobble/
├── app/                  # self-contained runtime
│   ├── wob.py            # bootstrap
│   ├── wobble/           # Python package + __pycache__
│   ├── docs/
│   ├── LICENSE
│   └── VERSION
└── install.json          # manifest + SHA-256 hashes
~/.local/bin/wob          # generated launcher
```

Installer options:

| Flag | Effect |
|:---|:---|
| `--root DIR` | Install directory (default `~/.local/share/wobble`) |
| `--bin DIR` | Launcher directory (default `~/.local/bin`) |
| `--source DIR` | Install from a specific checkout |
| `--force` | Replace an existing foreign `wob` executable |
| `--no-completion` | Skip bash/zsh completion files |
| `--no-path` | Do not edit shell startup files |

### Verify, upgrade, uninstall

```bash
wob self status      # install mode, app dir, launcher, source independence
wob self verify      # SHA-256 check of every installed file
wob self install     # reinstall/upgrade from the current checkout
wob self uninstall   # remove Wobble, keep projects (--purge removes config too)
```

Or, without a working `wob` command:

```bash
sh uninstall.sh              # preserves projects and ~/.wobble
sh uninstall.sh --purge -y   # also removes registry, plugins, keystore, config
```

> **The source checkout is disposable.** After `sh install.sh`, `rm -rf ~/wobble` does not affect the installed `wob` command. `wob self verify` reads only the installed app and its manifest.

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
wob web dev                # framework dev server (localhost)
wob web dev --lan          # expose the dev server on Wi-Fi
wob web preview            # zero-dependency static server + SPA fallback
wob web preview --lan      # preview from a laptop/tablet on the same Wi-Fi
```

`wob web preview` prints a compact ASCII card and falls back to `index.html` for client-side routes, so routers such as React Router survive a page refresh:

```
+--[ web preview ]-----------------------------------------------+
directory:   /data/data/com.termux/files/home/myfrontend
local:       http://localhost:3000/
+----------------------------------------------------------------+
  Locked to localhost. To test from another device: wob preview --lan
  Secrets (.env, .git, keys) and directory listings are always blocked.
  Press Ctrl+C to stop.
```

With `--lan`, Wobble adds the detected network URL and prints an explicit exposure warning:

```
network:     http://192.168.1.75:3000/
  [!] LAN exposure is ON: anyone on this Wi-Fi can read these files.
```

The server is threaded, uses HTTP/1.1 keep-alive, gzip-compresses text assets with a small in-memory cache, and refuses to serve dotfiles, credential files, directory listings, traversal paths, or symlinked files that escape the project root.

---

## Command reference

| Command | Description |
|:---|:---|
| `wob doctor [--quick]` | Run system diagnostics; `--quick` skips slow tool version probes |
| `wob create android <name> [-p pkg]` | Scaffold a native Android Gradle project |
| `wob create web <name> [-f framework]` | Scaffold a web app (`vite`, `react`, `vue`, `svelte`, `nextjs`, `python`, `php`, `static`) |
| `wob project list / info / open / remove` | Manage the project registry |
| `wob android build / clean / info / limitations` | Native Android workflows and constraint report |
| `wob apk build [--release]` | Compile the project into an APK |
| `wob apk list / info [file]` | Locate and parse APK metadata |
| `wob apk install [file] [--method auto\|termux-open\|am\|adb]` | Open the Android package installer |
| `wob apk share [file] [--dest dir]` | Export the APK to shared Download storage |
| `wob apk sign [file] [--keystore ks] [--alias a]` | Sign an APK with `apksigner` (password via `WOBBLE_KS_PASS`) |
| `wob apk clean` | Delete generated APKs |
| `wob web dev [-p port] [--host h] [--lan]` | Start the framework development server |
| `wob web build / test` | Production build / test suite |
| `wob web preview [-p port] [--dir d] [--lan]` | Hardened static preview with SPA fallback |
| `wob web serve [-p port] [--lan]` | Static HTTP file server |
| `wob deps install [stack] / add / remove / doctor / list` | Unified dependency management (`pkg`, `npm`, `pip`, `composer`) |
| `wob plugin list / info <name>` | Inspect framework plugins and prerequisites |
| `wob config list / get / set` | Persistent user configuration |
| `wob self status / verify` | Inspect the standalone installation and verify file hashes |
| `wob self install / uninstall` | Install or remove the standalone runtime |
| `wob install` / `wob uninstall` | Short aliases for `self install` / `self uninstall` |
| `wob clean [--all] [-y]` | Remove build artifacts and caches (`--all` adds `node_modules`, Gradle caches; prompts first) |
| `wob completion [bash\|zsh]` | Generate a shell completion script |
| `wob build / dev / preview` | Project-type-aware shortcuts |
| `wob banner / about` | Print the ASCII wordmark / version, install mode, and environment |
| `wob version / help` | Print the version or the full help text (fast path) |
| `wob update` | Show installed version, install mode, and upgrade command |
| `wob schema` | Dump the machine-readable CLI schema |

Global flags: `--json`, `--no-color`, `--verbose`, `--version`. They may appear before or after the subcommand (`wob --json doctor` and `wob doctor --json` are equivalent). `wob version` and `wob help` are aliases for the corresponding flags.

---

## Performance

Version 1.2.0 adds a fast path that answers `wob --version`, `wob version`, and plain `wob` without importing `argparse`, `difflib`, or any subcommand module. Representative measurements on an x86_64 Linux sandbox with Python 3.11 (median of repeated cold-process runs; phone timings will be higher, but the ratios hold):

| Command | 1.1.0 | 1.2.0 | Change |
|:---|---:|---:|---:|
| `wob --version` (`python -m` entry) | 38 ms | **22 ms** | ~42% faster |
| `wob --version` (launcher) | 42 ms | **25 ms** | ~40% faster |
| `wob doctor --json` (full) | 146 ms | 146 ms | — |
| `wob doctor --json --quick` | — | **58 ms** | ~2.5× faster than full |
| `wob plugin list` | 52 ms | 54 ms | parity after adding security checks |

Additional optimizations:

- **Standalone launcher without subprocesses.** The generated launcher is a single POSIX-shell script with no `ls`/`expr`/`dirname`/`pwd` forks; the development launcher was rewritten the same way.
- **Precompiled bytecode.** The installer runs `compileall` over the entire package, so the first run after installation does not pay compilation cost.
- **Module-name plugin imports.** Nine built-in plugins load through `importlib.import_module` (bytecode-cached, deterministic order) instead of parsing files from arbitrary paths on every invocation. `typing` was removed from the startup-critical modules.
- **Memoized environment probes.** Termux detection, architecture, Android SDK candidates, Java homes, Android properties, and the LAN IP are computed once per process; config lookup no longer creates directories as a side effect.
- **Concurrent diagnostics.** `wob doctor` still probes tool versions in parallel, and `--quick` replaces eight subprocess probes with pure PATH lookups.
- **Gzip + keep-alive preview.** Text assets ≥1 KiB are compressed (typical 5 KB HTML: ~40 bytes on the wire) and cached in memory; HTTP/1.1 keep-alive avoids a new connection per asset.
- **Threaded preview server.** Each request runs on a daemon thread, so one slow client cannot stall others.
- **Pruned file walks.** APK discovery, project metrics, cleans, and greps skip `.git`, `node_modules`, `.gradle`, `.venv`, and similar directories; symlinked build directories are never followed.
- **Memory-safe Gradle defaults.** Builds run with `--no-daemon`, `-Xmx1024m`, and parallel workers disabled to survive Android's low-memory killer.[5]

---

## Stability and data safety

- **Atomic writes.** Configuration, the project registry, and `wobble.json` specs are written to a temporary file and renamed into place, so an interrupted write cannot truncate them.
- **Non-destructive corruption recovery.** Invalid JSON is preserved before defaults are restored. Existing `.corrupt.bak` files are never overwritten; later backups use a numeric suffix. Failure to preserve the original stops recovery rather than risking data loss.
- **No silent persistence failures.** Configuration and registry write errors are raised with the affected path and a permissions/disk-space hint. In-memory configuration changes roll back if the disk write fails. CLI values arrive as strings; known port and boolean settings are validated and coerced before saving.
- **Specific subprocess failures.** Missing executables produce 127, non-executable files 126, timeouts 124, and interrupts 130. Results include an `error_code`, partial output where available, and a recovery hint; invalid working directories are identified before launch.
- **Graceful interrupts.** `Ctrl+C` terminates the child process group, exits with status 130, and escalates cleanup if a child does not stop promptly. Finite commands have timeouts; interactive servers intentionally run until stopped.
- **Defensive project state.** Stale registry entries are pruned in a batched write, malformed entries are ignored, and a malformed `wobble.json` produces an explicit repair error instead of being misreported as “no project found.”
- **Honest partial completion.** Cleanup reports every path it could not remove and exits non-zero. Project creation can succeed with an explicit registry warning rather than falsely reporting that scaffolding failed.
- **Strict input validation.** Project names must match `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`, Android package IDs must be reverse-DNS identifiers, and TCP ports must be in `1..65535`. Scaffolding into a symlink is refused.

### Error output and exit codes

Human errors include a concise cause and, when known, a `Hint:` with the next recovery step. Tracebacks are opt-in through `--verbose`. In JSON mode, argument errors and expected runtime errors use the same machine-readable contract:

```json
{
  "success": false,
  "error": "Port 3000 is already in use on 127.0.0.1.",
  "error_code": "port_in_use",
  "hint": "Stop the other server or try 'wob web preview --port 3001'."
}
```

`error_code` is stable for scripts; `details` may add the path, port, usage, or exception type. Domain commands may additionally include `stdout`, `stderr`, `returncode`, recovery `warnings`, and per-file `errors`. A long-running command that already emitted a startup document writes any later error document to stderr, keeping stdout parseable.

| Exit | Meaning |
|---:|:---|
| `0` | Success, or a documented clean cancellation |
| `1` | Operational, validation, filesystem, or unexpected runtime failure |
| `2` | Invalid CLI arguments or configuration value |
| `124` | External command timeout, when propagated by the command |
| `126` | Executable permission failure, when propagated |
| `127` | Required executable not found, when propagated |
| `130` | Interrupted by `Ctrl+C` |

### Security hardening (1.2.0)

- **Localhost by default.** `wob web dev`, `wob preview`, and `wob web preview` bind to `127.0.0.1` unless `--lan`/`--host 0.0.0.0` is explicit. Generated Vite/React/Vue/Svelte configs use `127.0.0.1` as well, with a comment explaining `wob dev --lan`.
- **Secret-file blocking.** The preview server refuses dotfiles and known credential paths (`.env*`, `.git/`, `.npmrc`, `.netrc`, `local.properties`, `id_rsa*`, `*.pem`, `*.key`, `*.jks`, `*.keystore`, `*.p12`, …).
- **No directory listings.** Directories without an `index.html` return a compact ASCII 404 instead of exposing the file tree.
- **No symlink escapes.** Every request is resolved and checked against the served root; symlinks pointing outside are treated as 404.
- **Traversal defence.** Literal and percent-encoded `..` segments are rejected before the filesystem is touched.
- **Untrusted plugins are constrained.** User plugins load only from a private (non-group/world-writable) directory, cannot be symlinks, must use a safe lowercase name, and cannot shadow built-in plugins. Set `WOBBLE_ALLOW_UNSAFE_PLUGINS=1` only if you understand the risk.
- **Keystore passwords are not argv.** `wob apk sign` passes credentials to `apksigner` through `WOBBLE_KS_PASS` (`env:` protocol), so they do not appear in `ps` output.
- **Installation integrity.** The installer writes a SHA-256 manifest and `wob self verify` re-hashes the installed tree. `wob self status` reports whether the runtime is source-independent, and the launcher refuses to run from a damaged app directory with a clear reinstall message.
- **Safer uninstall.** Uninstall removes only files that carry Wobble's generated-launcher marker or completion signature; foreign executables are reported and kept. Project directories are never touched; config is kept unless `--purge` is given.
- **Full test coverage.** 161 automated tests verify parsing, scaffolding, detection, executor behavior, doctor reporting, JSON success/error contracts, installer isolation, preview security, plugin trust rules, persistence recovery, partial failures, input validation, and the safety properties above.

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
python3 tests/run_tests.py     # 161 tests, standard library only
sh install.sh                  # install the standalone application
```

The test suite is dependency-free (standard-library `unittest` only) and covers the installer (including deleting the source checkout and re-running the launcher), preview security, plugin trust rules, and input validation. Project layout, plugin authoring, and platform-specific notes are documented in [`docs/`](docs/) — see [`docs/architecture.md`](docs/architecture.md), [`docs/plugins.md`](docs/plugins.md), [`docs/android_guide.md`](docs/android_guide.md), and [`docs/web_guide.md`](docs/web_guide.md). Contributions follow [`CONTRIBUTING.md`](CONTRIBUTING.md).

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
