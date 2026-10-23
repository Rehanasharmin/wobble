# Wobble System Architecture

## 1. High-Level Concept

```
Termux Environment (Android ARM64 / x86_64)
    │
    ▼
Installed launcher  ~/.local/bin/wob          Development launcher  bin/wob
    │                                              │
    └──────────────► wobble/bootstrap.py ◄─────────┘
                       │  fast paths: --version, bare `wob`
                       ▼
                 wobble/cli.py (argparse + dispatch)
                       │
    ├─► Core Engine (`wobble/core/`)
    │     ├── Installer & Manifest (`installer.py`)
    │     ├── ASCII Theme (`theme.py`)
    │     ├── Shell Completions (`completions.py`)
    │     ├── Dynamic Context Detector (`context.py`)
    │     ├── Environment Doctor (`doctor.py`) ──► Probe Cache (`probecache.py`)
    │     ├── Self-Check Engine (`selfcheck.py`) ──► Health Ledger (`health.py`)
    │     ├── Machine Schema (`schema.py`)
    │     ├── Safe Executor (`executor.py`)
    │     ├── Atomic File Utilities (`fsutil.py`)
    │     └── Structured Logger / JSON Formatter (`logger.py`)
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
    │     └── User Custom Plugins (`~/.wobble/plugins/`, trust-checked)
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
    │     └── Hardened Preview Server (gzip, keep-alive, secret blocking)
    │
    └─► Unified Dependency Manager (`wobble/deps/`)
          ├── Termux Packages (`pkg` / `apt`)
          ├── Node (`npm` / `pnpm` / `yarn`)
          ├── Python (`pip`)
          ├── PHP (`composer`)
          └── Android SDK (`sdkmanager`)
```

## 2. Standalone installation model

Wobble 1.2.0 stopped symlinking `~/.local/bin/wob` into a Git checkout. The
installer (`wobble/core/installer.py`) now performs a real application install:

```
~/.local/share/wobble/
├── app/                      # copied runtime (no .git, no tests, no uploads)
│   ├── wob.py                # bootstrap: sys.path + wobble.bootstrap.run()
│   ├── wobble/               # package
│   │   └── __pycache__/      # precompiled by compileall
│   ├── docs/
│   ├── LICENSE
│   ├── README.md
│   └── VERSION
└── install.json              # manifest: version, hashes, launchers, completions
~/.local/bin/wob              # generated POSIX-sh launcher (absolute APP path)
```

Properties:

- **Source independence.** `install.json` records the source path for diagnostics
  only. Nothing in the installed runtime imports from, or resolves paths inside,
  the checkout.
- **Atomic upgrades.** The runtime is staged in `<root>/.app.tmp-<pid>`, then
  swapped: `app → .app.old`, staging → `app`, `.app.old` removed. A crash cannot
  leave a half-written `app/`.
- **Integrity manifest.** Every installed source file is hashed (SHA-256) and
  sized. `wob self verify` re-hashes the tree; `__pycache__` is intentionally
  excluded so a Python version change does not produce false positives.
- **Self-discovery.** `running_install_root()` recognises
  `<root>/app/wobble/core/installer.py` and returns `<root>`, so custom
  `--root` installs work without exporting environment variables.
- **Safe removal.** Uninstall deletes only files carrying Wobble's generated
  launcher/completion markers, plus the known runtime directories. Projects and
  `~/.wobble` are preserved unless `--purge` is passed.
- **Self-diagnosis.** `wob self status` runs `selfcheck.inspect()`, which reads
  only filesystem metadata (manifest, sizes, launcher target, bytecode coverage,
  PATH resolution, config JSON, free space) in a couple of milliseconds.
  `--deep` adds parallel SHA-256 verification and imports the heavy subcommand
  modules to prove the runtime still loads. Each finding has a stable `code` and
  a machine-readable `status` (`ok` / `info` / `warning` / `critical`).
- **Honest repair.** `selfcheck.repair()` rewrites launchers, recompiles missing
  bytecode, regenerates completions, removes install debris, and backs up corrupt
  config/registry files. It never rewrites manifest hashes unless
  `--accept-current` is passed explicitly, so damage cannot be hidden.
- **Health memory.** `health.py` keeps a capped incident ledger
  (`~/.wobble/health/incidents.json`) and a doctor snapshot
  (`~/.wobble/health/doctor-baseline.json`). The bootstrap records unexpected
  exceptions; the doctor diffs each run against the snapshot to report
  regressions, recoveries, and long-standing failures.
- **Probe cache.** `probecache.py` stores tool version probes keyed by the
  executable's inode fingerprint (`st_dev`, `st_ino`, `mtime_ns`, `st_size`) with
  a one-hour TTL, so upgrading a tool invalidates itself and repeat doctor runs
  avoid subprocesses entirely.

## 3. Startup fast path

`python -m wobble` and the installed launcher both enter
`wobble/bootstrap.py:run()`:

1. No arguments → render the ASCII landing screen (no argparse).
2. `--version` / `-V` / `version` (± `--json`) → print and exit.
3. Anything else → import `wobble.cli` and parse.

Consequences:

- `argparse`, `difflib`, and subcommand modules are not imported for version or
  landing output.
- `difflib` is imported only on the typo-suggestion error path.
- `typing`, `json`, `hashlib`, `socket`, `tempfile`, `platform`, and
  `concurrent.futures` are imported lazily; a cold `wob self status` no longer
  pays for hashing, threading, or network machinery it does not use. A startup
  regression test (`tests/test_startup.py`) fails if a heavy module creeps back
  into the import path.
- Plugin modules are imported by module name in a fixed order, which also makes
  detection deterministic.
- Memoized probes (`lru_cache`) cover Termux detection, architecture, Android
  SDK candidates, Java homes, Android properties, and the LAN IP.
- Config lookup is side-effect free: `get_wobble_config_path()` no longer
  creates `~/.config/wobble` just because a command needed the path.

## 4. Preview server design

`wobble/web/preview.py` is a zero-dependency `ThreadingHTTPServer` handler:

- **Localhost by default**; `--lan` / `--host 0.0.0.0` is explicit and prints a
  Wi-Fi exposure warning.
- **Path resolution guard**: each request is resolved with `Path.resolve()` and
  must remain under the served root, blocking symlink escapes.
- **Blocklists** for dot-prefixed path components and credential filenames
  (`.env*`, `.git`, `.npmrc`, `.netrc`, `local.properties`, `id_rsa*`,
  `*.pem`, `*.key`, `*.jks`, `*.keystore`, `*.p12`, `*.sqlite`, `*.log`, …).
- **No directory listings**; directories without `index.html` return an ASCII
  404 card.
- **SPA fallback** for extension-less routes with an existing `index.html`.
- **HTTP/1.1 keep-alive**, `nosniff`, `no-referrer`, and `no-store` headers.
- **gzip** for compressible types ≥ 1 KiB, with a bounded LRU cache (64 entries,
  8 MiB) shared by worker threads.
- **ASCII startup card** showing local (and optionally network) URLs plus the
  security posture in plain language.

## 5. Dynamic Environment Resolution

Wobble never hardcodes paths. On every invocation:

- `$PREFIX` is inspected. If unset, `/data/data/com.termux/files/usr` or `sys.prefix` is resolved.
- `$HOME` is inspected.
- Architecture is detected via `platform.machine()` and normalized (`aarch64`, `arm`, `x86_64`, `x86`).
- Toolchains are discovered dynamically in standard search paths (`$HOME/.local/bin`, `$HOME/bin`, `$PREFIX/bin`, `/system/bin`).
- Android SDK candidates are checked in `$ANDROID_HOME`, `$ANDROID_SDK_ROOT`, `$PREFIX/share/android-sdk`, and `~/android-sdk`.
- Memory (`/proc/meminfo`) and storage (`shutil.disk_usage`) are inspected safely.

## 6. ASCII output layer

`wobble/core/theme.py` provides the entire visual identity with no dependencies:

- `BANNER_ART` — 5-line ASCII wordmark, padded to a rectangle, coloured with a
  256/16-colour gradient when the terminal supports it.
- `rule()` / `box()` — `+--[ title ]----+` headers and content boxes, ANSI-aware.
- `badge()` — `[ OK ]`, `[WARN]`, `[MISS]`, `[FAIL]`, `[INFO]`, `[RUN ]`, `[SKIP]`.
- `progress_bar()` — `[#####>------] 42%`.
- `supports_color()` — respects `NO_COLOR`, `FORCE_COLOR`, `TERM=dumb`, and tty.

Every renderer produces identical layout with colour disabled, so `--no-color`,
piped output, JSON mode, and test captures stay plain ASCII.

## 7. Error handling and failure propagation

- `wobble/core/errors.py` defines expected operational errors with a stable
  `error_code`, optional recovery `hint`/`details`, and an exit status.
- The custom argument parser raises `UsageError` instead of exiting before the
  logger exists. Consequently even `wob web dev --port nope --json` returns one
  valid JSON failure document and exit 2.
- The CLI catches expected errors separately from unexpected exceptions. Human
  output gets concise causes and hints; `--verbose` opts into tracebacks. JSON
  mode records handler errors and emits a fallback failure document whenever a
  non-zero handler did not already produce one.
- `ExecutionResult` normalizes subprocess failures (`124`, `126`, `127`, `130`)
  and retains partial stdout/stderr. Streaming commands capture child output in
  JSON mode and terminate the whole child process group on interruption.
- Config/registry writes are never silently discarded. Corrupt files are moved
  to non-overwriting backups before recovery; write failures surface with paths
  and rollback in-memory config changes. Current-project operations use strict
  `wobble.json` parsing while broad directory scans remain tolerant.
- Preview startup and cleanup operations return real failure statuses. Partial
  deletion includes a per-path `errors` array instead of reporting success.

## 8. Security Model

- **Zero Root Requirements**: Wobble runs entirely within standard user permissions.
- **W^X Compliance**: All builds and scripts execute from app-private storage.
- **Process Isolation**: Commands run via `subprocess.run` / `Popen` with argument arrays to eliminate shell injection vulnerabilities.
- **Input validation**: Project names and Android package IDs are whitelisted before any template is rendered; scaffolding into symlinks is refused; cleans never follow symlinked build directories.
- **Untrusted plugins**: user plugins require a private directory and file mode, must use safe names, cannot be symlinks, and cannot shadow built-ins. `WOBBLE_ALLOW_UNSAFE_PLUGINS=1` is the documented escape hatch.
- **No secret leakage**: previews block credential files; keystore passwords reach `apksigner` through the `WOBBLE_KS_PASS` environment variable rather than argv.
- **Privacy First**: No telemetry, analytics, or outbound background network calls.

## 9. Test topology

`tests/run_tests.py` discovers standard-library `unittest` modules:

| File | Focus |
|:---|:---|
| `test_installer.py` | install layout, manifest, source deletion, tamper detection, uninstall |
| `test_hardening.py` | name/package validation, symlink targets, clean symlink safety |
| `test_error_handling.py` | JSON failures, exit codes, subprocess diagnostics, strict specs, persistence and partial failures |
| `test_preview_security.py` | blocked paths, traversal, gzip cache |
| `test_theme.py` | ASCII purity, widths, colour toggling |
| `test_plugins.py` | built-in discovery plus user-plugin trust rules |
| `test_cli.py`, `test_json_output.py`, `test_schema.py`, `test_ux.py` | parser, JSON, schema, completion, clean |
| `test_android.py`, `test_apk.py`, `test_web.py`, `test_deps.py`, `test_doctor.py`, `test_context.py`, `test_executor.py`, `test_fsutil.py`, `test_project.py`, `test_framework_detection.py` | domain behaviour and safety |
| `test_selfcheck.py`, `test_health.py`, `test_startup.py` | self-health checks, repair, incident ledger, probe cache, regression diffs, startup import hygiene |
