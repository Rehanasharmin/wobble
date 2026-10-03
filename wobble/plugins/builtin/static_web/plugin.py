"""
Wobble Static Web Framework Plugin
Provides scaffolding and local preview for pure HTML5, CSS3, and JavaScript projects.
Zero external package dependencies required.
"""

from pathlib import Path
from typing import List, Dict, Any, Optional

from wobble.plugins.base import BasePlugin
from wobble.project.spec import ProjectSpec


class StaticWebPlugin(BasePlugin):
    name = "static_web"
    version = "1.0.0"
    description = "Modern HTML5 / CSS3 / JavaScript static web application"
    category = "web"
    required_system_packages = []
    required_tools = []

    def detect(self, project_path: Path) -> bool:
        if (project_path / "index.html").exists() and not (project_path / "package.json").exists():
            return True
        return False

    def create_project(self, name: str, target_dir: Path, options: Optional[Dict[str, Any]] = None) -> bool:
        target_dir.mkdir(parents=True, exist_ok=True)
        css_dir = target_dir / "css"
        js_dir = target_dir / "js"
        css_dir.mkdir(exist_ok=True)
        js_dir.mkdir(exist_ok=True)

        index_html = target_dir / "index.html"
        with open(index_html, "w", encoding="utf-8") as f:
            f.write(f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{name} - Built with Wobble</title>
    <link rel="stylesheet" href="css/style.css">
</head>
<body>
    <div class="container">
        <header>
            <div class="badge">Wobble on Termux</div>
            <h1>{name}</h1>
            <p class="subtitle">Fast, lightweight web development directly on your Android device.</p>
        </header>

        <main>
            <section class="card">
                <h2>⚡ Quick Start</h2>
                <p>Edit <code>index.html</code>, <code>css/style.css</code>, or <code>js/app.js</code> to see live updates.</p>
                <div class="actions">
                    <button id="counter-btn" class="btn">Clicks: 0</button>
                    <button id="ping-btn" class="btn secondary">Test Device API</button>
                </div>
                <div id="output-log" class="log-box">Status: Ready</div>
            </section>
        </main>

        <footer>
            <p>Powered by <strong>Wobble</strong> &bull; Zero dependencies required</p>
        </footer>
    </div>
    <script src="js/app.js"></script>
</body>
</html>
""")

        style_css = css_dir / "style.css"
        with open(style_css, "w", encoding="utf-8") as f:
            f.write("""* {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: #0d1117;
    color: #e6edf3;
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 100vh;
    padding: 20px;
}

.container {
    max-width: 600px;
    width: 100%;
}

header {
    text-align: center;
    margin-bottom: 24px;
}

.badge {
    display: inline-block;
    background: #238636;
    color: #ffffff;
    font-size: 12px;
    font-weight: 600;
    padding: 4px 10px;
    border-radius: 20px;
    margin-bottom: 12px;
}

h1 {
    font-size: 2.2rem;
    margin-bottom: 8px;
    background: linear-gradient(135deg, #58a6ff, #bc8cff);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

.subtitle {
    color: #8b949e;
    font-size: 1rem;
}

.card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 12px;
    padding: 24px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
}

.card h2 {
    font-size: 1.3rem;
    margin-bottom: 12px;
    color: #f0f6fc;
}

.card p {
    color: #c9d1d9;
    margin-bottom: 20px;
    line-height: 1.5;
}

code {
    background: #21262d;
    padding: 2px 6px;
    border-radius: 4px;
    color: #79c0ff;
    font-family: monospace;
}

.actions {
    display: flex;
    gap: 12px;
    margin-bottom: 16px;
}

.btn {
    background: #238636;
    color: white;
    border: none;
    padding: 10px 18px;
    border-radius: 6px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.2s ease;
}

.btn:hover {
    background: #2ea043;
}

.btn.secondary {
    background: #21262d;
    color: #c9d1d9;
    border: 1px solid #30363d;
}

.btn.secondary:hover {
    background: #30363d;
}

.log-box {
    background: #0d1117;
    border: 1px solid #30363d;
    padding: 12px;
    border-radius: 6px;
    font-family: monospace;
    font-size: 13px;
    color: #7ee787;
}

footer {
    text-align: center;
    margin-top: 24px;
    color: #8b949e;
    font-size: 0.85rem;
}
""")

        app_js = js_dir / "app.js"
        with open(app_js, "w", encoding="utf-8") as f:
            f.write("""// Wobble Client-Side Script
document.addEventListener("DOMContentLoaded", () => {
    let count = 0;
    const counterBtn = document.getElementById("counter-btn");
    const pingBtn = document.getElementById("ping-btn");
    const logBox = document.getElementById("output-log");

    counterBtn.addEventListener("click", () => {
        count++;
        counterBtn.textContent = `Clicks: ${count}`;
        logBox.textContent = `Status: Counter incremented to ${count}`;
    });

    pingBtn.addEventListener("click", () => {
        const time = new Date().toLocaleTimeString();
        const ua = navigator.userAgent;
        logBox.textContent = `Pinged at ${time} | Agent: ${ua.slice(0, 35)}...`;
    });
});
""")

        gitignore = target_dir / ".gitignore"
        with open(gitignore, "w", encoding="utf-8") as f:
            f.write(""".DS_Store
dist/
build/
""")

        spec = ProjectSpec(
            name=name,
            project_type="web",
            framework="static_web",
            path=target_dir,
            description="Pure HTML5/CSS3/JS static application",
            scripts={
                "preview": "wob web preview",
                "serve": "wob web serve"
            }
        )
        spec.save()
        return True

    def get_dev_command(self, project_path: Path, options: Optional[Dict[str, Any]] = None) -> Optional[List[str]]:
        port = (options or {}).get("port", 3000)
        return ["python3", "-m", "http.server", str(port)]

    def get_run_command(self, project_path: Path, options: Optional[Dict[str, Any]] = None) -> Optional[List[str]]:
        return self.get_dev_command(project_path, options)
