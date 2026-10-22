# Wobble Plugin Development Guide

Wobble features an extensible plugin system. New frameworks, toolchains, and
project archetypes can be integrated without modifying Wobble's core codebase.

---

## 1. Plugin locations

Wobble discovers plugins from two places:

1. **Built-in plugins** — `wobble/plugins/builtin/<name>/plugin.py`
2. **User plugins** — `~/.wobble/plugins/<name>/plugin.py` (or the directory in
   the `custom_plugins_dir` config key)

Built-ins are imported by module name in a fixed order, so framework detection
is deterministic and benefits from bytecode caching:

| Order | Plugin | Category |
|:---:|:---|:---|
| 1 | `android` | android |
| 2 | `nextjs` | web |
| 3 | `react` | web |
| 4 | `vue` | web |
| 5 | `svelte` | web |
| 6 | `vite` | web |
| 7 | `python_web` | web |
| 8 | `php` | web |
| 9 | `static_web` | web |

Specific frameworks are checked before generic ones, so a React project with a
Vite config resolves to `react`, not `vite`.

Framework aliases are resolved before lookup:

| Alias | Plugin |
|:---|:---|
| `python`, `flask`, `fastapi`, `py` | `python_web` |
| `static`, `html`, `html5` | `static_web` |
| `next` | `nextjs` |
| `reactjs` | `react` |
| `vuejs` | `vue` |
| `sveltejs` | `svelte` |

---

## 2. Trust rules for user plugins

User plugins are executable Python code, so Wobble treats them as **untrusted**:

- The plugin directory name must match `^[a-z][a-z0-9_]{1,31}$`.
- The plugin directory and `plugin.py` must not be group- or world-writable:

  ```bash
  chmod 700 ~/.wobble/plugins/myframework
  chmod 600 ~/.wobble/plugins/myframework/plugin.py
  ```

- Neither the directory nor the file may be a symlink.
- `plugin.py` must be a regular file inside the directory (no path escape).
- The plugin's `name` attribute must be a safe lowercase identifier and must not
  collide with a built-in plugin. Built-ins always win; a user plugin that tries
  to shadow one is skipped with a warning.
- Set `WOBBLE_ALLOW_UNSAFE_PLUGINS=1` only during local development if you
  deliberately need looser permissions. Do not set it on shared devices.

A rejected plugin is reported with a `[!]` warning by `wob plugin list` and never
crashes the core.

---

## 3. Implementing a plugin

Create `~/.wobble/plugins/myframework/plugin.py`:

```python
from pathlib import Path
from typing import Any, Dict, List, Optional

from wobble.plugins.base import BasePlugin
from wobble.project.spec import ProjectSpec


class MyFrameworkPlugin(BasePlugin):
    name = "myframework"
    version = "1.0.0"
    description = "Support for My Custom Framework"
    category = "web"  # "web", "android", or "general"
    required_system_packages = ["nodejs"]
    required_tools = ["node", "npm"]

    def detect(self, project_path: Path) -> bool:
        """Return True if project_path matches this framework."""
        return (project_path / "myframework.config.json").exists()

    def create_project(
        self,
        name: str,
        target_dir: Path,
        options: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Scaffold project files."""
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "index.html").write_text("<h1>Custom Framework</h1>")

        spec = ProjectSpec(
            name=name,
            project_type="web",
            framework=self.name,
            path=target_dir,
            description="My framework project",
        )
        spec.save()
        return True

    def get_dev_command(
        self,
        project_path: Path,
        options: Optional[Dict[str, Any]] = None,
    ) -> Optional[List[str]]:
        port = (options or {}).get("port", 3000)
        host = (options or {}).get("host", "127.0.0.1")
        return ["npm", "run", "dev", "--", "--host", host, "--port", str(port)]

    def get_build_command(
        self,
        project_path: Path,
        options: Optional[Dict[str, Any]] = None,
    ) -> Optional[List[str]]:
        return ["npm", "run", "build"]
```

Notes:

- Return **argument lists**, never shell strings; Wobble executes them with
  `subprocess` without a shell.
- Default dev servers to `127.0.0.1`; honour `options["host"]` so
  `wob web dev --lan` can expose them deliberately.
- `wob create` validates project names (`[A-Za-z0-9][A-Za-z0-9._-]{0,63}`) and
  Android package IDs before calling `create_project`. If you interpolate the
  name into HTML/XML/JSON, still escape it for defence in depth.

---

## 4. Verifying your plugin

```bash
wob plugin list
wob plugin info myframework
wob create web myapp --framework myframework
```

`wob plugin list` shows metadata and prerequisites. `wob plugin info` also
reports whether the host has every `required_tools` entry. In JSON mode both
commands return structured data:

```bash
wob plugin list --json
wob plugin info myframework --json
```

---

## 5. Testing plugins

Add a standard-library `unittest` module under `tests/` (for example
`tests/test_myframework.py`) that:

1. Creates the marker file in a temporary directory and asserts `detect()`
   returns `True`.
2. Calls `create_project()` into a temporary directory and asserts the expected
   files and `wobble.json` exist.
3. Asserts dev/build commands are argument lists containing the expected
   executable and port/host flags.

Run the whole suite with:

```bash
python3 tests/run_tests.py
```
