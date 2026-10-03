"""
Wobble PHP Framework Plugin
Supports PHP applications with built-in development web server and Composer.
"""

from pathlib import Path
from typing import List, Dict, Any, Optional

from wobble.plugins.base import BasePlugin
from wobble.project.spec import ProjectSpec


class PhpPlugin(BasePlugin):
    name = "php"
    version = "1.0.0"
    description = "PHP web application with built-in development server"
    category = "web"
    required_system_packages = ["php"]
    required_tools = ["php"]

    def detect(self, project_path: Path) -> bool:
        if (project_path / "index.php").exists() or (project_path / "composer.json").exists():
            return True
        return False

    def create_project(self, name: str, target_dir: Path, options: Optional[Dict[str, Any]] = None) -> bool:
        target_dir.mkdir(parents=True, exist_ok=True)
        public_dir = target_dir / "public"
        public_dir.mkdir(exist_ok=True)

        index_php = public_dir / "index.php"
        with open(index_php, "w", encoding="utf-8") as f:
            f.write(f"""<?php
header('Content-Type: text/html; charset=utf-8');
?>
<!DOCTYPE html>
<html>
<head>
    <title>{name} - PHP on Termux</title>
    <style>
        body {{ font-family: sans-serif; background: #0f172a; color: #f8fafc; padding: 40px; text-align: center; }}
        .card {{ background: #1e293b; max-width: 500px; margin: 0 auto; padding: 30px; border-radius: 12px; }}
        h1 {{ color: #787cb5; }}
        .info {{ background: #0f172a; padding: 12px; border-radius: 6px; font-family: monospace; font-size: 14px; text-align: left; }}
    </style>
</head>
<body>
    <div class="card">
        <h1>🐘 PHP + Wobble</h1>
        <p>PHP runtime execution directly in Termux.</p>
        <div class="info">
            <div><strong>PHP Version:</strong> <?php echo phpversion(); ?></div>
            <div><strong>Server Time:</strong> <?php echo date('Y-m-d H:i:s'); ?></div>
            <div><strong>OS:</strong> <?php echo PHP_OS; ?></div>
        </div>
    </div>
</body>
</html>
""")

        # Root index.php router for built-in server
        root_index = target_dir / "index.php"
        with open(root_index, "w", encoding="utf-8") as f:
            f.write("""<?php
require_once __DIR__ . '/public/index.php';
""")

        spec = ProjectSpec(
            name=name,
            project_type="web",
            framework="php",
            path=target_dir,
            description="PHP web project",
            scripts={
                "dev": "wob web dev",
                "preview": "wob web preview"
            },
            dependencies={
                "system": ["php"],
                "project": {}
            }
        )
        spec.save()
        return True

    def get_dev_command(self, project_path: Path, options: Optional[Dict[str, Any]] = None) -> Optional[List[str]]:
        port = (options or {}).get("port", 3000)
        host = (options or {}).get("host", "0.0.0.0")
        target_dir = "public" if (project_path / "public").is_dir() else "."
        return ["php", "-S", f"{host}:{port}", "-t", target_dir]

    def get_run_command(self, project_path: Path, options: Optional[Dict[str, Any]] = None) -> Optional[List[str]]:
        return self.get_dev_command(project_path, options)
