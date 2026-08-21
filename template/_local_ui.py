"""Tiny authenticated loopback UI host for portable MadCowork modules."""

from __future__ import annotations

import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


class LocalUiServer:
    def __init__(self, module_name: str, ui_dir: Path, actions: dict):
        self.module_name = module_name
        self.ui_dir = ui_dir.resolve()
        self.actions = actions
        self.token = secrets.token_urlsafe(32)
        self._server = None
        self._thread = None

    def open(self) -> dict:
        if self._server is None:
            owner = self

            class Handler(BaseHTTPRequestHandler):
                server_version = "MadCoworkModuleUI/1"

                def log_message(self, _format, *_args):
                    return

                def _headers(self, status: int, content_type: str):
                    self.send_response(status)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Referrer-Policy", "no-referrer")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.send_header("X-Frame-Options", "SAMEORIGIN")
                    self.send_header(
                        "Content-Security-Policy",
                        "default-src 'self'; script-src 'self'; style-src 'self'; "
                        "connect-src 'self'; img-src 'self' data:; frame-ancestors 'self'",
                    )

                def _json(self, status: int, payload: dict):
                    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                    self._headers(status, "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

                def _local_host(self) -> bool:
                    host = self.headers.get("Host", "").lower()
                    return host.startswith("127.0.0.1:") or host.startswith("localhost:")

                def do_GET(self):
                    if not self._local_host():
                        self._json(403, {"ok": False, "error": "loopback host required"})
                        return
                    path = unquote(urlsplit(self.path).path)
                    relative = "index.html" if path in {"", "/"} else path.lstrip("/")
                    candidate = (owner.ui_dir / relative).resolve()
                    if owner.ui_dir not in candidate.parents or not candidate.is_file():
                        self._json(404, {"ok": False, "error": "not found"})
                        return
                    content_types = {
                        ".html": "text/html; charset=utf-8",
                        ".css": "text/css; charset=utf-8",
                        ".js": "text/javascript; charset=utf-8",
                        ".svg": "image/svg+xml",
                        ".png": "image/png",
                    }
                    body = candidate.read_bytes()
                    self._headers(200, content_types.get(candidate.suffix.lower(), "application/octet-stream"))
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

                def do_POST(self):
                    if not self._local_host():
                        self._json(403, {"ok": False, "error": "loopback host required"})
                        return
                    if urlsplit(self.path).path != "/api/action":
                        self._json(404, {"ok": False, "error": "not found"})
                        return
                    if not secrets.compare_digest(
                        self.headers.get("X-MadCowork-Module-Token", ""), owner.token
                    ):
                        self._json(403, {"ok": False, "error": "invalid module UI token"})
                        return
                    try:
                        length = int(self.headers.get("Content-Length", "0"))
                        if length < 1 or length > 1024 * 1024:
                            raise ValueError("request body must be between 1 byte and 1 MiB")
                        request = json.loads(self.rfile.read(length))
                        action = str(request.get("action") or "")
                        args = request.get("args") or {}
                        if action not in owner.actions:
                            raise ValueError(f"unsupported UI action: {action}")
                        if not isinstance(args, dict):
                            raise ValueError("args must be an object")
                        result = owner.actions[action](args)
                        self._json(200, {"ok": True, "result": result})
                    except Exception as exc:
                        self._json(400, {"ok": False, "error": str(exc)})

            self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
            self._thread.start()

        port = self._server.server_address[1]
        return {
            "ok": True,
            "module": self.module_name,
            "url": f"http://127.0.0.1:{port}/?token={self.token}",
            "note": "Open this loopback URL in MadCowork's browser panel. It remains available while the trusted plugin process is running.",
        }
