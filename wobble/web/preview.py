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


def find_free_port(start_port: int = 3000, max_attempts: int = 50) -> int:
    """Find an available TCP port starting from start_port."""
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", port))
                return port
            except OSError:
                continue
    return start_port


def start_static_preview(directory: Path, port: Optional[int] = None, host: str = "0.0.0.0"):
    """
    Launch a lightweight, zero-dependency static preview server.
    Displays localhost and LAN URLs for cross-device testing.
    """
    logger = get_logger()
    actual_port = port if port else find_free_port(3000)
    lan_ip = get_lan_ip()

    serve_dir = str(directory.resolve())

    class CustomHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=serve_dir, **kwargs)

        def log_message(self, format, *args):
            # Clean minimal request logging
            sys.stdout.write(f"  [Preview] {self.address_string()} - {args[0]}\n")

    # Allow socket reuse to prevent port-in-use errors on quick restart
    socketserver.TCPServer.allow_reuse_address = True

    try:
        with socketserver.TCPServer((host, actual_port), CustomHandler) as httpd:
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
        logger.error(f"Failed to start web server on port {actual_port}: {e}")
