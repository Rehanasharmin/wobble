"""
Wobble Vite Framework Plugin
Fast modern web bundler supporting Vanilla JS/TS, React, Vue, Svelte.
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional

from wobble.plugins.base import BasePlugin
from wobble.project.spec import ProjectSpec


class VitePlugin(BasePlugin):
    name = "vite"
    version = "1.0.0"
    description = "Next-generation modern web tooling with Vite"
    category = "web"
    required_system_packages = ["nodejs"]
    required_tools = ["node", "npm"]

    def detect(self, project_path: Path) -> bool:
        pkg_json = project_path / "package.json"
        if pkg_json.exists():
            try:
                with open(pkg_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                    return "vite" in deps
            except Exception:
                pass
        return (project_path / "vite.config.js").exists() or (project_path / "vite.config.ts").exists()

    def create_project(self, name: str, target_dir: Path, options: Optional[Dict[str, Any]] = None) -> bool:
        target_dir.mkdir(parents=True, exist_ok=True)
        src_dir = target_dir / "src"
        src_dir.mkdir(exist_ok=True)

        package_json = target_dir / "package.json"
        with open(package_json, "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "name": name,
                "private": True,
                "version": "0.1.0",
                "type": "module",
                "scripts": {
                    "dev": "vite --host",
                    "build": "vite build",
                    "preview": "vite preview --host"
                },
                "devDependencies": {
                    "vite": "^5.2.0"
                }
            }, indent=2))

        vite_config = target_dir / "vite.config.js"
        with open(vite_config, "w", encoding="utf-8") as f:
            f.write("""import { defineConfig } from 'vite';

export default defineConfig({
  server: {
    host: '0.0.0.0',
    port: 3000
  }
});
""")

        index_html = target_dir / "index.html"
        with open(index_html, "w", encoding="utf-8") as f:
            f.write(f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{name} - Vite on Termux</title>
</head>
<body>
  <div id="app"></div>
  <script type="module" src="/src/main.js"></script>
</body>
</html>
""")

        main_js = src_dir / "main.js"
        with open(main_js, "w", encoding="utf-8") as f:
            f.write("""import './style.css';

document.querySelector('#app').innerHTML = `
  <div class="card">
    <h1>⚡ Vite + Termux</h1>
    <p>Modern fast frontend development running in Wobble.</p>
    <button id="counter" type="button">Count: 0</button>
  </div>
`;

let count = 0;
const btn = document.querySelector('#counter');
btn.addEventListener('click', () => {
  count++;
  btn.innerHTML = `Count: ${count}`;
});
""")

        style_css = src_dir / "style.css"
        with open(style_css, "w", encoding="utf-8") as f:
            f.write("""body {
  margin: 0;
  display: flex;
  place-items: center;
  min-width: 320px;
  min-height: 100vh;
  background: #242424;
  color: #fff;
  font-family: system-ui, sans-serif;
  justify-content: center;
}

.card {
  padding: 2em;
  text-align: center;
  background: #1a1a1a;
  border-radius: 12px;
  border: 1px solid #333;
}

button {
  border-radius: 8px;
  border: 1px solid transparent;
  padding: 0.6em 1.2em;
  font-size: 1em;
  font-weight: 500;
  background-color: #646cff;
  color: #fff;
  cursor: pointer;
  transition: border-color 0.25s;
}

button:hover {
  background-color: #535bf2;
}
""")

        spec = ProjectSpec(
            name=name,
            project_type="web",
            framework="vite",
            path=target_dir,
            description="Vite web project created with Wobble",
            scripts={
                "dev": "wob web dev",
                "build": "wob web build",
                "preview": "wob web preview"
            },
            dependencies={
                "system": ["nodejs"],
                "project": {"devDependencies": {"vite": "^5.2.0"}}
            }
        )
        spec.save()
        return True

    def get_dev_command(self, project_path: Path, options: Optional[Dict[str, Any]] = None) -> Optional[List[str]]:
        port = (options or {}).get("port")
        host = (options or {}).get("host", "0.0.0.0")
        cmd = ["npx", "vite", "--host", host]
        if port:
            cmd.extend(["--port", str(port)])
        return cmd

    def get_build_command(self, project_path: Path, options: Optional[Dict[str, Any]] = None) -> Optional[List[str]]:
        return ["npx", "vite", "build"]

    def get_test_command(self, project_path: Path, options: Optional[Dict[str, Any]] = None) -> Optional[List[str]]:
        return ["npm", "test"]

    def get_clean_command(self, project_path: Path, options: Optional[Dict[str, Any]] = None) -> Optional[List[str]]:
        return ["rm", "-rf", "dist", ".vite"]
