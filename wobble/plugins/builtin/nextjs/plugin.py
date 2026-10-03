"""
Wobble Next.js Framework Plugin
Supports Next.js full-stack React frameworks.
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional

from wobble.plugins.base import BasePlugin
from wobble.project.spec import ProjectSpec


class NextjsPlugin(BasePlugin):
    name = "nextjs"
    version = "1.0.0"
    description = "Next.js React full-stack framework"
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
                    return "next" in deps
            except Exception:
                pass
        return (project_path / "next.config.js").exists() or (project_path / "next.config.mjs").exists()

    def create_project(self, name: str, target_dir: Path, options: Optional[Dict[str, Any]] = None) -> bool:
        target_dir.mkdir(parents=True, exist_ok=True)
        pages_dir = target_dir / "pages"
        pages_dir.mkdir(exist_ok=True)

        package_json = target_dir / "package.json"
        with open(package_json, "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "name": name,
                "version": "0.1.0",
                "private": True,
                "scripts": {
                    "dev": "next dev -H 0.0.0.0",
                    "build": "next build",
                    "start": "next start -H 0.0.0.0"
                },
                "dependencies": {
                    "next": "^14.1.0",
                    "react": "^18.2.0",
                    "react-dom": "^18.2.0"
                }
            }, indent=2))

        index_page = pages_dir / "index.js"
        with open(index_page, "w", encoding="utf-8") as f:
            f.write(f"""export default function Home() {{
  return (
    <main style={{{{ padding: '40px', fontFamily: 'sans-serif', background: '#000', color: '#fff', minHeight: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}}}>
      <h1 style={{{{ fontSize: '2.5rem', marginBottom: '16px' }}}}>▲ Next.js + Wobble</h1>
      <p style={{{{ color: '#888' }}}}>Full-stack SSR React applications running in Termux.</p>
    </main>
  );
}}
""")

        spec = ProjectSpec(
            name=name,
            project_type="web",
            framework="nextjs",
            path=target_dir,
            description="Next.js full-stack web project",
            scripts={
                "dev": "wob web dev",
                "build": "wob web build",
                "preview": "wob web preview"
            },
            dependencies={
                "system": ["nodejs"],
                "project": {"next": "^14.1.0"}
            }
        )
        spec.save()
        return True

    def get_dev_command(self, project_path: Path, options: Optional[Dict[str, Any]] = None) -> Optional[List[str]]:
        port = (options or {}).get("port", 3000)
        host = (options or {}).get("host", "0.0.0.0")
        return ["npx", "next", "dev", "-H", host, "-p", str(port)]

    def get_build_command(self, project_path: Path, options: Optional[Dict[str, Any]] = None) -> Optional[List[str]]:
        return ["npx", "next", "build"]

    def get_run_command(self, project_path: Path, options: Optional[Dict[str, Any]] = None) -> Optional[List[str]]:
        port = (options or {}).get("port", 3000)
        host = (options or {}).get("host", "0.0.0.0")
        return ["npx", "next", "start", "-H", host, "-p", str(port)]
