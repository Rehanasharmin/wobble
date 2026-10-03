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
├── bin/wob               # Shell entrypoint launcher
├── wobble/
│   ├── core/             # Context, logger, executor, doctor, schema, config
│   ├── project/          # Project manager, wobble.json specification
│   ├── android/          # Native Android build coordinator, APK inspector & installer
│   ├── web/              # Web dev servers, framework detection, LAN preview
│   ├── deps/             # Unified package manager routing
│   └── plugins/          # Plugin loader, BasePlugin, built-in framework plugins
├── tests/                # Automated unit test suite
├── docs/                 # In-depth architectural & workflow guides
└── install.sh            # Safe single-command installer
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

## 4. Running the Test Suite

Run the full test suite inside Termux or any Linux environment:
```bash
python3 tests/run_tests.py
```
All tests must pass before submitting a pull request.
