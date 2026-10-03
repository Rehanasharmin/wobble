"""
Wobble React Framework Plugin
Supports React web development via Vite or Create-React-App structures.
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional

from wobble.plugins.base import BasePlugin
from wobble.project.spec import ProjectSpec


class ReactPlugin(BasePlugin):
    name = "react"
    version = "1.0.0"
    description = "React modern user interface application"
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
                    return "react" in deps
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
                    "react": "^18.2.0",
                    "react-dom": "^18.2.0"
                },
                "devDependencies": {
                    "@vitejs/plugin-react": "^4.2.1",
                    "vite": "^5.2.0"
                }
            }, indent=2))

        vite_config = target_dir / "vite.config.js"
        with open(vite_config, "w", encoding="utf-8") as f:
            f.write("""import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
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
  <title>{name} - React on Termux</title>
</head>
<body>
  <div id="root"></div>
  <script type="module" src="/src/main.jsx"></script>
</body>
</html>
""")

        main_jsx = src_dir / "main.jsx"
        with open(main_jsx, "w", encoding="utf-8") as f:
            f.write("""import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App.jsx';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
""")

        app_jsx = src_dir / "App.jsx"
        with open(app_jsx, "w", encoding="utf-8") as f:
            f.write("""import React, { useState } from 'react';

export default function App() {
  const [count, setCount] = useState(0);

  return (
    <div className="container">
      <h1>⚛️ React + Wobble</h1>
      <p>Building reactive web applications inside Termux.</p>
      <button onClick={() => setCount(count + 1)}>
        Count is {count}
      </button>
    </div>
  );
}
""")

        index_css = src_dir / "index.css"
        with open(index_css, "w", encoding="utf-8") as f:
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
.container {
  text-align: center;
  padding: 2rem;
  background: #1e1e1e;
  border-radius: 12px;
  border: 1px solid #333;
}
button {
  background: #61dafb;
  color: #000;
  border: none;
  padding: 10px 20px;
  font-size: 16px;
  border-radius: 6px;
  cursor: pointer;
  font-weight: bold;
}
""")

        spec = ProjectSpec(
            name=name,
            project_type="web",
            framework="react",
            path=target_dir,
            description="React web application with Vite",
            scripts={
                "dev": "wob web dev",
                "build": "wob web build",
                "preview": "wob web preview"
            },
            dependencies={
                "system": ["nodejs"],
                "project": {"react": "^18.2.0"}
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
