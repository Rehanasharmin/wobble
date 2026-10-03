# Wobble Plugin Development Guide

Wobble features an extensible plugin system. New frameworks, toolchains, and project archetypes can be integrated without modifying Wobble's core codebase.

---

## 1. Plugin Location

Wobble discovers plugins from two locations:
1. **Built-in Plugins**: `wobble/plugins/builtin/<plugin_name>/plugin.py`
2. **User Custom Plugins**: `~/.wobble/plugins/<plugin_name>/plugin.py`

Any directory inside these folders containing a `plugin.py` that subclasses `BasePlugin` is automatically loaded at runtime.

---

## 2. Implementing a Plugin

Create `~/.wobble/plugins/myframework/plugin.py`:

```python
from pathlib import Path
from typing import List, Dict, Any, Optional
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

    def create_project(self, name: str, target_dir: Path, options: Optional[Dict[str, Any]] = None) -> bool:
        """Scaffold project files."""
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "index.html").write_text("<h1>Custom Framework</h1>")
        
        # Save wobble.json
        spec = ProjectSpec(
            name=name,
            project_type="web",
            framework=self.name,
            path=target_dir,
            description="My framework project"
        )
        spec.save()
        return True

    def get_dev_command(self, project_path: Path, options: Optional[Dict[str, Any]] = None) -> Optional[List[str]]:
        port = (options or {}).get("port", 3000)
        return ["npm", "run", "dev", "--", "--port", str(port)]

    def get_build_command(self, project_path: Path, options: Optional[Dict[str, Any]] = None) -> Optional[List[str]]:
        return ["npm", "run", "build"]
```

---

## 3. Verifying Your Plugin

Run:
```bash
wob plugin list
wob plugin info myframework
```
Wobble will display your plugin's metadata, prerequisites status, and required tools.
You can now create projects using your plugin:
```bash
wob create web myapp --framework myframework
```
