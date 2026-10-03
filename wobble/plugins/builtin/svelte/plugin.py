"""
Wobble Svelte Framework Plugin
Supports Svelte modern lightweight frontend development with Vite.
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional

from wobble.plugins.base import BasePlugin
from wobble.project.spec import ProjectSpec


class SveltePlugin(BasePlugin):
    name = "svelte"
    version = "1.0.0"
    description = "Svelte cybernetically enhanced web apps with Vite"
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
                    return "svelte" in deps
            except Exception:
                pass
        return False

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
                    "@sveltejs/vite-plugin-svelte": "^3.0.2",
                    "svelte": "^4.2.12",
                    "vite": "^5.2.0"
                }
            }, indent=2))

        vite_config = target_dir / "vite.config.js"
        with open(vite_config, "w", encoding="utf-8") as f:
            f.write("""import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default defineConfig({
  plugins: [svelte()],
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
  <title>{name} - Svelte on Termux</title>
</head>
<body>
  <div id="app"></div>
  <script type="module" src="/src/main.js"></script>
</body>
</html>
""")

        main_js = src_dir / "main.js"
        with open(main_js, "w", encoding="utf-8") as f:
            f.write("""import App from './App.svelte';

const app = new App({
  target: document.getElementById('app'),
});

export default app;
""")

        app_svelte = src_dir / "App.svelte"
        with open(app_svelte, "w", encoding="utf-8") as f:
            f.write("""<script>
  let count = 0;
  function handleClick() {
    count += 1;
  }
</script>

<main>
  <h1>🧡 Svelte + Wobble</h1>
  <p>Truly reactive components compiled for high performance.</p>
  <button on:click={handleClick}>
    Clicks: {count}
  </button>
</main>

<style>
  main {
    text-align: center;
    padding: 2em;
    max-width: 400px;
    margin: 100px auto;
    background: #1e1e1e;
    color: #fff;
    border-radius: 12px;
    border: 1px solid #333;
  }
  button {
    background: #ff3e00;
    color: white;
    border: none;
    padding: 10px 20px;
    border-radius: 6px;
    font-size: 16px;
    cursor: pointer;
  }
</style>
""")

        gitignore = target_dir / ".gitignore"
        with open(gitignore, "w", encoding="utf-8") as f:
            f.write("""node_modules/
dist/
dist-ssr/
.vite/
*.local
.DS_Store
""")

        spec = ProjectSpec(
            name=name,
            project_type="web",
            framework="svelte",
            path=target_dir,
            description="Svelte web application with Vite",
            scripts={
                "dev": "wob web dev",
                "build": "wob web build",
                "preview": "wob web preview"
            },
            dependencies={
                "system": ["nodejs"],
                "project": {"devDependencies": {"svelte": "^4.2.12"}}
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

    def get_clean_command(self, project_path: Path, options: Optional[Dict[str, Any]] = None) -> Optional[List[str]]:
        return ["rm", "-rf", "dist", ".vite"]
