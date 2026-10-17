"""
Wobble Web Preview Server & LAN Testing
Provides zero-dependency HTTP server with automatic port discovery and LAN IP broadcast.
"""

import sys
import socket
import http.server
import socketserver
from pathlib import Path
from typing import Optional

from wobble.core.context import get_lan_ip
from wobble.core.logger import get_logger

# Directories we are never willing to serve preview content from inside a project
_HIDDEN_PARTS = {".git", ".wobble", "__pycache__", "node_modules"}


def find_free_port(start_port: int = 3000, max_attempts: int = 50) -> Optional[int]:
    """
    Find an available TCP port starting from start_port.
    Returns None when the whole range is occupied so callers can fail loudly
    instead of silently binding a colliding port.
    """
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", port))
                return port
            except OSError:
                continue
    return None


class _ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """Serve requests on separate threads so slow clients cannot stall others."""
    daemon_threads = True
    allow_reuse_address = True


def start_static_preview(directory: Path, port: Optional[int] = None, host: str = "0.0.0.0"):
    """
    Launch a lightweight, zero-dependency static preview server.
    Displays localhost and LAN URLs for cross-device testing.
    """
    logger = get_logger()
    serve_dir = str(directory.resolve())

    # Explicit ports must be honored exactly; auto mode picks the next free one.
    if port:
        actual_port = port
    else:
        free = find_free_port(3000)
        if free is None:
            logger.error("No free TCP port found in range 3000-3050. Close other servers and retry.")
            return
        actual_port = free

    lan_ip = get_lan_ip()

    class CustomHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=serve_dir, **kwargs)

        def do_GET(self):
            # SPA Fallback: if requesting a route that doesn't exist on disk and has no extension, serve index.html
            req_path = self.path.split("?")[0].split("#")[0].lstrip("/")
            parts = [p for p in req_path.split("/") if p not in ("", ".")]
            if ".." in parts:
                # Never probe outside the served directory
                return super().do_GET()
            local_target = Path(serve_dir).joinpath(*parts) if parts else Path(serve_dir)
            try:
                exists = local_target.exists()
            except OSError:
                exists = False
            if not exists and "." not in Path(req_path).name:
                index_fallback = Path(serve_dir) / "index.html"
                if index_fallback.is_file():
                    self.path = "/index.html"
            return super().do_GET()

        def log_message(self, format, *args):
            if not logger.json_mode:
                sys.stdout.write(f"  [Preview] {self.address_string()} - {args[0]}\n")

    try:
        httpd = _ThreadingHTTPServer((host, actual_port), CustomHandler)
    except OSError as e:
        if getattr(e, "errno", None) in (98, 48, 10048):  # address already in use
            logger.error(
                f"Port {actual_port} is already in use. "
                f"Try 'wob web preview -p {actual_port + 1}' or stop the other server."
            )
        else:
            logger.error(f"Failed to start web server on port {actual_port}: {e}")
        return

    try:
        with httpd:
            if not logger.json_mode:
                print("\n" + "=" * 54)
                print("         ⚡ WOBBLE WEB PREVIEW RUNNING")
                print("=" * 54)
                print(f"  Directory: {serve_dir}")
                print(f"  \033[1m➜ Local:\033[0m    http://localhost:{actual_port}/")
                if lan_ip and lan_ip != "127.0.0.1":
                    print(f"  \033[1m➜ Network:\033[0m  http://{lan_ip}:{actual_port}/")
                print("-" * 54)
                print("  Tip: Open the Network URL on any computer, tablet,")
                print("       or phone connected to the same Wi-Fi network!")
                print("  Press Ctrl+C to stop.")
                print("=" * 54 + "\n")
            else:
                logger.json_output({
                    "status": "running",
                    "port": actual_port,
                    "host": host,
                    "local_url": f"http://localhost:{actual_port}/",
                    "network_url": f"http://{lan_ip}:{actual_port}/" if lan_ip else None,
                    "directory": serve_dir
                })

            httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("\nWeb preview server stopped.")
    except Exception as e:
        logger.error(f"Web server error on port {actual_port}: {e}")
