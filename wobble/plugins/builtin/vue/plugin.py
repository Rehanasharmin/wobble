"""
Wobble Vue Framework Plugin
Supports Vue 3 single file component development with Vite.
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional

from wobble.plugins.base import BasePlugin
from wobble.project.spec import ProjectSpec


class VuePlugin(BasePlugin):
    name = "vue"
    version = "1.0.0"
    description = "Vue 3 progressive frontend framework with Vite"
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
                    return "vue" in deps
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
                "dependencies": {
                    "vue": "^3.4.21"
                },
                "devDependencies": {
                    "@vitejs/plugin-vue": "^5.0.4",
                    "vite": "^5.2.0"
                }
            }, indent=2))

        vite_config = target_dir / "vite.config.js"
        with open(vite_config, "w", encoding="utf-8") as f:
            f.write("""import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

export default defineConfig({
  plugins: [vue()],
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
  <title>{name} - Vue on Termux</title>
</head>
<body>
  <div id="app"></div>
  <script type="module" src="/src/main.js"></script>
</body>
</html>
""")

        main_js = src_dir / "main.js"
        with open(main_js, "w", encoding="utf-8") as f:
            f.write("""import { createApp } from 'vue';
import App from './App.vue';
import './style.css';

createApp(App).mount('#app');
""")

        app_vue = src_dir / "App.vue"
        with open(app_vue, "w", encoding="utf-8") as f:
            f.write("""<script setup>
import { ref } from 'vue';

const count = ref(0);
</script>

<template>
  <div class="box">
    <h1>💚 Vue 3 + Wobble</h1>
    <p>Single file components developing smoothly on Termux.</p>
    <button @click="count++">Count is {{ count }}</button>
  </div>
</template>

<style scoped>
.box {
  background: #1e1e1e;
  padding: 2rem;
  border-radius: 12px;
  text-align: center;
  border: 1px solid #333;
}
button {
  background: #42b883;
  color: #fff;
  border: none;
  padding: 10px 20px;
  font-size: 16px;
  border-radius: 6px;
  cursor: pointer;
}
</style>
""")

        style_css = src_dir / "style.css"
        with open(style_css, "w", encoding="utf-8") as f:
            f.write("""body {
  margin: 0;
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  background: #121212;
  color: #fff;
  font-family: system-ui, sans-serif;
}
""")

        spec = ProjectSpec(
            name=name,
            project_type="web",
            framework="vue",
            path=target_dir,
            description="Vue 3 web application with Vite",
            scripts={
                "dev": "wob web dev",
                "build": "wob web build",
                "preview": "wob web preview"
            },
            dependencies={
                "system": ["nodejs"],
                "project": {"vue": "^3.4.21"}
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
