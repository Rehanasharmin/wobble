"""
Wobble Python Web Framework Plugin
Supports Flask, FastAPI, and standard Python WSGI/ASGI web servers.
"""

from pathlib import Path
from typing import List, Dict, Any, Optional

from wobble.plugins.base import BasePlugin
from wobble.project.spec import ProjectSpec


class PythonWebPlugin(BasePlugin):
    name = "python_web"
    version = "1.0.0"
    description = "Python Web application (Flask / FastAPI / http.server)"
    category = "web"
    required_system_packages = ["python"]
    required_tools = ["python3"]

    def detect(self, project_path: Path) -> bool:
        if (project_path / "app.py").exists() or (project_path / "main.py").exists() or (project_path / "requirements.txt").exists():
            return True
        return False

    def create_project(self, name: str, target_dir: Path, options: Optional[Dict[str, Any]] = None) -> bool:
        target_dir.mkdir(parents=True, exist_ok=True)
        templates_dir = target_dir / "templates"
        static_dir = target_dir / "static"
        templates_dir.mkdir(exist_ok=True)
        static_dir.mkdir(exist_ok=True)

        app_py = target_dir / "app.py"
        with open(app_py, "w", encoding="utf-8") as f:
            f.write(f"""# Python Web Server (Flask / Standalone)
import os
import sys

try:
    from flask import Flask, render_template_string, jsonify
    app = Flask(__name__)

    HTML_TEMPLATE = \"\"\"
    <!DOCTYPE html>
    <html>
    <head>
        <title>{name} - Wobble Python</title>
        <style>
            body {{ font-family: sans-serif; background: #0d1117; color: #c9d1d9; text-align: center; padding: 50px; }}
            .card {{ background: #161b22; max-width: 500px; margin: 0 auto; padding: 30px; border-radius: 12px; border: 1px solid #30363d; }}
            h1 {{ color: #58a6ff; }}
            a {{ color: #58a6ff; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h1>🐍 Python Web + Wobble</h1>
            <p>Running Flask on Android Termux.</p>
            <p>API Endpoint: <a href="/api/info">/api/info</a></p>
        </div>
    </body>
    </html>
    \"\"\"

    @app.route("/")
    def index():
        return render_template_string(HTML_TEMPLATE)

    @app.route("/api/info")
    def api_info():
        return jsonify({{"app": "{name}", "platform": sys.platform, "status": "running"}})

    if __name__ == "__main__":
        port = int(os.environ.get("PORT", 3000))
        app.run(host="0.0.0.0", port=port, debug=True)

except ImportError:
    # Fallback to standard library http.server if Flask is not installed
    from http.server import HTTPServer, SimpleHTTPRequestHandler
    class Handler(SimpleHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/api/info":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{{"status": "ok", "notice": "Install flask for full router: wob deps add flask"}}')
                return
            super().do_GET()

    if __name__ == "__main__":
        port = int(os.environ.get("PORT", 3000))
        print(f"Serving HTTP on 0.0.0.0 port {{port}} (Install Flask: pip install flask)...")
        server = HTTPServer(("0.0.0.0", port), Handler)
        server.serve_forever()
""")

        index_html = target_dir / "index.html"
        with open(index_html, "w", encoding="utf-8") as f:
            f.write(f"""<!DOCTYPE html>
<html>
<head><title>{name}</title></head>
<body style="background:#111;color:#eee;font-family:sans-serif;text-align:center;padding:50px;">
    <h1>🐍 {name}</h1>
    <p>Python web server initialized.</p>
</body>
</html>
""")

        req_txt = target_dir / "requirements.txt"
        with open(req_txt, "w", encoding="utf-8") as f:
            f.write("flask>=3.0.0\n")

        gitignore = target_dir / ".gitignore"
        with open(gitignore, "w", encoding="utf-8") as f:
            f.write("""__pycache__/
*.py[cod]
*$py.class
.venv/
venv/
env/
.env
.DS_Store
""")

        spec = ProjectSpec(
            name=name,
            project_type="web",
            framework="python_web",
            path=target_dir,
            description="Python web application",
            scripts={
                "dev": "wob web dev",
                "preview": "wob web preview"
            },
            dependencies={
                "system": ["python"],
                "project": {"requirements": ["flask"]}
            }
        )
        spec.save()
        return True

    def get_dev_command(self, project_path: Path, options: Optional[Dict[str, Any]] = None) -> Optional[List[str]]:
        return ["python3", "app.py"]

    def get_run_command(self, project_path: Path, options: Optional[Dict[str, Any]] = None) -> Optional[List[str]]:
        return ["python3", "app.py"]

    def get_clean_command(self, project_path: Path, options: Optional[Dict[str, Any]] = None) -> Optional[List[str]]:
        return ["rm", "-rf", "__pycache__", ".pytest_cache"]
