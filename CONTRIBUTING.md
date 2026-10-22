# Contributing to Wobble

Thank you for your interest in making Termux a first-class mobile development workstation!

## 1. Development Philosophy

1. **Lightweight & Portable**: Wobble uses Python's standard library with zero external pip dependencies for its core CLI. This guarantees instant installation on any ARM64, ARM, or x86 Android device without pip wheel compilation errors.
2. **Honest Capabilities**: Never fake functionality. If an Android feature requires a specific tool, permission, or user action, diagnose it clearly and explain the workaround.
3. **No Root Requirement**: Wobble must remain 100% usable on non-rooted production Android devices.
4. **AI-Friendly Interfaces**: Always support `--json` structured outputs for machine parsing.

## 2. Directory Layout

```
wobble/
├── bin/wob               # Development launcher (source checkout only)
├── wobble/
│   ├── bootstrap.py      # --version / landing fast path
│   ├── cli.py            # argparse definitions and command dispatch
│   ├── core/             # installer, theme, completions, context, logger, executor, doctor, schema, config
│   ├── project/          # Project manager, wobble.json specification
│   ├── android/          # Native Android build coordinator, APK inspector & installer
│   ├── web/              # Web dev servers, framework detection, hardened preview
│   ├── deps/             # Unified package manager routing
│   └── plugins/          # Plugin loader, BasePlugin, built-in framework plugins
├── tests/                # Automated unit test suite (128 tests, <1 s)
├── docs/                 # In-depth architectural & workflow guides
├── install.sh            # Standalone installer (copy + manifest + launcher)
└── uninstall.sh          # Standalone uninstaller (projects preserved)
```

Installed layout (created by `sh install.sh`, never committed):

```
~/.local/share/wobble/app/         # runtime copy + __pycache__
~/.local/share/wobble/install.json # SHA-256 manifest
~/.local/bin/wob                   # generated launcher
```

## 3. Adding a New Framework Plugin

To add support for a new web or mobile framework (e.g. Flutter, Astro, Remix, Django):
1. Create a directory in `wobble/plugins/builtin/<framework_name>/`.
2. Implement `plugin.py` subclassing `BasePlugin` from `wobble.plugins.base`.
3. Define:
   - `detect(project_path: Path) -> bool`
   - `create_project(name: str, target_dir: Path, options: dict) -> bool`
   - `get_dev_command(...) -> List[str]`
   - `get_build_command(...) -> List[str]`
4. Add automated tests in `tests/test_plugins.py` and `tests/test_framework_detection.py`.
5. Keep `get_dev_command()` bound to `options.get("host", "127.0.0.1")` so LAN exposure stays opt-in via `--lan`.

User plugins are untrusted: the loader enforces private directory/file modes, safe lowercase names, no symlinks, and no shadowing of built-ins. Do not weaken those checks in a pull request; add tests under `tests/test_plugins.py` instead.

## 4. Running the Test Suite

Run the full test suite inside Termux or any Linux environment:
```bash
python3 tests/run_tests.py
```
All tests must pass before submitting a pull request. Security-sensitive changes
(input validation, preview routing, installer file handling, plugin loading,
subprocess execution) need a regression test in `tests/test_hardening.py`,
`tests/test_preview_security.py`, `tests/test_installer.py`, or
`tests/test_plugins.py`.

Verify the standalone installer as well:

```bash
sh install.sh --root /tmp/wobble-test --bin /tmp/wobble-test/bin --no-path --no-completion
rm -rf /tmp/wobble-test-src      # or the checkout you installed from
/tmp/wobble-test/bin/wob self verify
```
