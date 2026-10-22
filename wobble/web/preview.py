"""
Wobble Web Preview Server & LAN Testing
A zero-dependency, threaded static server with:

* pure-ASCII startup card and 404 page
* optional gzip compression with a small in-memory cache
* HTTP/1.1 keep-alive for fast asset loading
* defence in depth: no directory listings, no dotfiles, no secret files,
  no symlink escapes, and localhost-only by default
"""

import gzip
import io
import os
import socket
import socketserver
import sys
import threading
import urllib.parse
from collections import OrderedDict
from http.server import SimpleHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional, Tuple

from wobble.core.context import get_lan_ip
from wobble.core.errors import PreviewError
from wobble.core.logger import get_logger
from wobble.core import theme

# Directories we are never willing to serve preview content from inside a project
_HIDDEN_PARTS = {
    ".git", ".hg", ".svn", ".wobble", ".idea", ".vscode", "__pycache__",
    "node_modules", ".gradle", ".venv", "venv",
}
# Files that commonly contain credentials. A dev server should never leak them,
# even when the project lives on a shared/public Wi-Fi network.
_BLOCKED_NAMES = {
    ".env", ".env.local", ".env.development", ".env.production", ".envrc",
    "local.properties", ".npmrc", ".yarnrc", ".netrc", ".pgpass", ".htpasswd",
    "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", "credentials", "credentials.json",
    "secrets.json", "secrets.yml", "secrets.yaml", "service-account.json",
    "debug.keystore", "keystore.jks", "release.keystore",
}
_BLOCKED_SUFFIXES = (
    ".pem", ".key", ".p12", ".pfx", ".jks", ".keystore", ".kdb", ".tfstate",
    ".sqlite", ".db", ".log",
)

_GZIP_TYPES = (
    "text/", "application/javascript", "application/json", "application/xml",
    "application/manifest+json", "application/xhtml+xml", "image/svg+xml",
)

# Small compressed-response cache shared by all worker threads.
_GZIP_CACHE: "OrderedDict[str, Tuple[int, int, bytes]]" = OrderedDict()
_GZIP_CACHE_LOCK = threading.Lock()
_GZIP_CACHE_MAX_ENTRIES = 64
_GZIP_CACHE_MAX_BYTES = 8 * 1024 * 1024


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


class _ThreadingHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    """Serve requests on separate threads so slow clients cannot stall others."""
    daemon_threads = True
    allow_reuse_address = True


def _is_blocked(url_path: str) -> bool:
    """Return True for traversal attempts, dotfiles, and secret-looking files."""
    try:
        parsed = urllib.parse.urlsplit(url_path)
        unquoted = urllib.parse.unquote(parsed.path)
    except Exception:
        return True

    raw = [part for part in unquoted.replace("\\", "/").split("/") if part not in ("", ".")]
    if ".." in raw:
        return True

    for part in raw:
        lowered = part.lower()
        if part.startswith(".") or lowered in _HIDDEN_PARTS or lowered in _BLOCKED_NAMES:
            return True

    if raw:
        name = raw[-1].lower()
        if name in _BLOCKED_NAMES or name.endswith(_BLOCKED_SUFFIXES):
            return True
        if name.startswith((".env.", "secret", "credential")):
            return True
    return False


def _gzip_payload(path: Path, stat_result: os.stat_result) -> Optional[bytes]:
    """Return cached gzip bytes for *path*, or None when not worth compressing."""
    key = str(path)
    stamp = (int(stat_result.st_mtime_ns), int(stat_result.st_size))
    with _GZIP_CACHE_LOCK:
        hit = _GZIP_CACHE.get(key)
        if hit and hit[0] == stamp[0] and hit[1] == stamp[1]:
            _GZIP_CACHE.move_to_end(key)
            return hit[2]

    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError:
        return None
    compressed = gzip.compress(raw, compresslevel=5, mtime=0)
    if len(compressed) >= len(raw) * 0.95:
        return None

    with _GZIP_CACHE_LOCK:
        _GZIP_CACHE[key] = (stamp[0], stamp[1], compressed)
        _GZIP_CACHE.move_to_end(key)
        total = sum(len(entry[2]) for entry in _GZIP_CACHE.values())
        while len(_GZIP_CACHE) > _GZIP_CACHE_MAX_ENTRIES or total > _GZIP_CACHE_MAX_BYTES:
            _, evicted = _GZIP_CACHE.popitem(last=False)
            total -= len(evicted[2])
    return compressed


def _accepted(request_headers, encoding: str) -> bool:
    value = request_headers.get("Accept-Encoding", "")
    return encoding in value.lower()


def start_static_preview(directory: Path, port: Optional[int] = None, host: str = "127.0.0.1") -> int:
    """Serve a directory, returning an exit code and raising startup failures."""
    logger = get_logger()
    serve_root = Path(directory).expanduser().resolve()
    if not serve_root.exists():
        raise PreviewError(
            f"Preview directory does not exist: {serve_root}",
            code="preview_directory_not_found",
            hint="Check --dir or build the project before starting the preview.",
            details={"directory": str(serve_root)},
        )
    if not serve_root.is_dir():
        raise PreviewError(
            f"Preview path is not a directory: {serve_root}",
            code="invalid_preview_directory",
            details={"directory": str(serve_root)},
        )
    serve_dir = str(serve_root)

    # Explicit ports must be honored exactly; auto mode picks the next free one.
    if port is not None:
        if not 1 <= port <= 65535:
            raise PreviewError(
                f"Invalid TCP port {port}; expected 1-65535.",
                code="invalid_port", exit_code=2,
            )
        actual_port = port
    else:
        free = find_free_port(3000)
        if free is None:
            raise PreviewError(
                "No free TCP port found in range 3000-3049.",
                code="no_free_port",
                hint="Close another server or choose an explicit port with --port.",
            )
        actual_port = free

    lan_ip = get_lan_ip()
    lan_enabled = host in ("0.0.0.0", "::", "")

    class WobblePreviewHandler(SimpleHTTPRequestHandler):
        # HTTP/1.1 enables keep-alive, which roughly halves the cost of loading
        # a page with dozens of small assets.
        protocol_version = "HTTP/1.1"
        server_version = "WobblePreview/1.2"
        sys_version = ""
        # Set before the base class handles the first request (it handles inside
        # __init__), otherwise translate_path() would run without a root.
        root = serve_root

        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=serve_dir, **kwargs)

        # -- security helpers -------------------------------------------
        def _blocked_target(self) -> Optional[str]:
            if _is_blocked(self.path):
                return "blocked path"
            return None

        def translate_path(self, path):
            """Resolve the request, then guarantee it stays inside the served root."""
            candidate = Path(super().translate_path(path))
            try:
                resolved = candidate.resolve()
                resolved.relative_to(self.root)
            except (OSError, ValueError):
                return str(self.root / "__wobble_forbidden__")
            return str(resolved)

        def list_directory(self, path):
            # Directory listings leak project structure (and are unnecessary).
            self.send_error(404, "Not Found")
            return None

        # -- response helpers --------------------------------------------
        def _not_found(self, reason: str = ""):
            body = (
                "\n"
                "  +------------------------------------------+\n"
                "  |            WOBBLE PREVIEW 404            |\n"
                "  +------------------------------------------+\n"
                "  |  That path is not part of this preview.  |\n"
                "  +------------------------------------------+\n\n"
            ).encode("utf-8")
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def end_headers(self):
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def send_head(self):
            blocked = self._blocked_target()
            if blocked:
                self._not_found(blocked)
                return None

            url = urllib.parse.urlsplit(self.path)
            path = self.translate_path(self.path)
            target = Path(path)

            if target.is_dir():
                if not url.path.endswith("/"):
                    self.send_response(301)
                    self.send_header("Location", url.path + "/")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return None
                index = None
                for name in ("index.html", "index.htm"):
                    candidate = target / name
                    if candidate.is_file():
                        index = candidate
                        break
                if index is None:
                    self._not_found("directory listing disabled")
                    return None
                target = index

            if not target.is_file():
                self._not_found()
                return None

            try:
                handle = open(target, "rb")
            except OSError:
                self._not_found()
                return None

            try:
                stat_result = os.fstat(handle.fileno())
                content_type = self.guess_type(str(target))
                compressible = any(content_type.startswith(prefix) for prefix in _GZIP_TYPES)
                compressed = None
                if compressible and stat_result.st_size >= 1024 and _accepted(self.headers, "gzip"):
                    compressed = _gzip_payload(target, stat_result)

                if compressed is not None:
                    handle.close()
                    handle = io.BytesIO(compressed)
                    self.send_response(200)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Encoding", "gzip")
                    self.send_header("Vary", "Accept-Encoding")
                    self.send_header("Content-Length", str(len(compressed)))
                    self.end_headers()
                    return handle

                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(stat_result.st_size))
                self.send_header("Last-Modified", self.date_time_string(stat_result.st_mtime))
                self.end_headers()
                return handle
            except Exception:
                try:
                    handle.close()
                except Exception:
                    pass
                raise

        def do_GET(self):
            if self._blocked_target():
                return self._not_found("blocked path")

            # SPA fallback: unknown extension-less routes get index.html.
            fs_path = Path(self.translate_path(self.path))
            if not fs_path.exists() and "." not in Path(urllib.parse.unquote(
                    urllib.parse.urlsplit(self.path).path)).name:
                index = self.root / "index.html"
                if index.is_file():
                    self.path = "/index.html"
            return super().do_GET()

        def log_message(self, format, *args):
            if not logger.json_mode:
                sys.stdout.write(f"  [preview] {self.address_string()} - {args[0]}\n")

    try:
        httpd = _ThreadingHTTPServer((host, actual_port), WobblePreviewHandler)
    except OSError as exc:
        if getattr(exc, "errno", None) in (98, 48, 10048):  # address already in use
            next_port = actual_port + 1 if actual_port < 65535 else 3000
            raise PreviewError(
                f"Port {actual_port} is already in use on {host}.",
                code="port_in_use",
                hint=f"Stop the other server or try 'wob web preview --port {next_port}'.",
                details={"host": host, "port": actual_port},
            ) from exc
        raise PreviewError(
            f"Cannot start web server on {host}:{actual_port}: {exc}",
            code="preview_bind_failed",
            hint="Check the host address and your network/port permissions.",
            details={"host": host, "port": actual_port},
        ) from exc

    try:
        with httpd:
            if not logger.json_mode:
                color = logger.use_color
                print()
                print(theme.rule("web preview", width=66, use_color=color))
                print(theme.kv("directory", serve_dir, use_color=color, width=12))
                print(theme.kv("local", theme.link(f"http://localhost:{actual_port}/", color),
                               use_color=color, width=12))
                if lan_enabled and lan_ip and lan_ip != "127.0.0.1":
                    print(theme.kv("network", theme.link(f"http://{lan_ip}:{actual_port}/", color),
                                   use_color=color, width=12))
                print(theme.rule("", width=66, use_color=color))
                if lan_enabled:
                    print(theme.paint(
                        "  [!] LAN exposure is ON: anyone on this Wi-Fi can read these files.",
                        theme.YELLOW, theme.BOLD, enabled=color))
                    print(theme.paint(
                        "      Use 'wob preview' (without --lan) on public networks.",
                        theme.DIM, enabled=color))
                else:
                    print(theme.paint(
                        "  Locked to localhost. To test from another device: wob preview --lan",
                        theme.DIM, enabled=color))
                print(theme.paint(
                    "  Secrets (.env, .git, keys) and directory listings are always blocked.",
                    theme.DIM, enabled=color))
                print(theme.paint("  Press Ctrl+C to stop.", theme.DIM, enabled=color))
                print()
                sys.stdout.flush()
            else:
                logger.json_output({
                    "status": "running",
                    "port": actual_port,
                    "host": host,
                    "local_url": f"http://localhost:{actual_port}/",
                    "network_url": f"http://{lan_ip}:{actual_port}/" if lan_ip else None,
                    "lan_enabled": lan_enabled,
                    "directory": serve_dir,
                })

            httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Web preview server stopped.")
        return 130
    except Exception as exc:
        raise PreviewError(
            f"Web server failed on port {actual_port}: {exc}",
            code="preview_runtime_failed",
            details={"host": host, "port": actual_port},
        ) from exc
    return 0
