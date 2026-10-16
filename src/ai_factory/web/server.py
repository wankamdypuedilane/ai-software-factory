"""A small local HTTP server for the web interface.

Standard library only. It listens on 127.0.0.1, and every API call must
carry the session token embedded in the page it served and come with a
local Host header, so another website open in the same browser cannot
drive the Factory (cross-site requests, DNS rebinding).
"""

from __future__ import annotations

import json
import secrets
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from ai_factory.web.service import FactoryService, ServiceError


TOKEN_HEADER = "X-Factory-Token"
MAX_BODY_BYTES = 1_000_000
STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
}


def _static_dir() -> Path:
    return Path(str(resources.files("ai_factory.web") / "static"))


def build_handler(
    service: FactoryService,
    token: str,
    port_holder: dict[str, int],
) -> type[BaseHTTPRequestHandler]:
    """Return a request handler bound to one service and one session token."""

    class Handler(BaseHTTPRequestHandler):
        server_version = "AIFactory"

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

        # -- helpers --------------------------------------------------------

        def _host_is_local(self) -> bool:
            host = (self.headers.get("Host") or "").split(":")[0].strip("[]")
            return host in {"127.0.0.1", "localhost", "::1"}

        def _send(
            self,
            status: int,
            body: bytes,
            content_type: str,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, payload: Any) -> None:
            self._send(
                status,
                json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                "application/json; charset=utf-8",
            )

        def _body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or 0)

            if length > MAX_BODY_BYTES:
                raise ServiceError("Requête trop volumineuse.")

            raw = self.rfile.read(length) if length else b"{}"

            try:
                data = json.loads(raw.decode("utf-8") or "{}")
            except ValueError as error:
                raise ServiceError("Requête invalide.") from error

            if not isinstance(data, dict):
                raise ServiceError("Requête invalide.")

            return data

        def _authorized(self) -> bool:
            return self._host_is_local() and secrets.compare_digest(
                self.headers.get(TOKEN_HEADER, ""),
                token,
            )

        # -- routing --------------------------------------------------------

        def do_GET(self) -> None:  # noqa: N802
            if not self._host_is_local():
                self._json(HTTPStatus.FORBIDDEN, {"error": "Accès refusé."})
                return

            url = urlparse(self.path)

            if not url.path.startswith("/api/"):
                self._serve_static(url.path)
                return

            if not self._authorized():
                self._json(HTTPStatus.FORBIDDEN, {"error": "Accès refusé."})
                return

            self._dispatch("GET", url.path, parse_qs(url.query), {})

        def do_POST(self) -> None:  # noqa: N802
            url = urlparse(self.path)

            if not self._authorized():
                self._json(HTTPStatus.FORBIDDEN, {"error": "Accès refusé."})
                return

            try:
                body = self._body()
            except ServiceError as error:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
                return

            self._dispatch("POST", url.path, {}, body)

        def _serve_static(self, path: str) -> None:
            name = "index.html" if path in {"", "/"} else path.lstrip("/")

            if "/" in name or name.startswith(".") or not name:
                self._json(HTTPStatus.NOT_FOUND, {"error": "Introuvable."})
                return

            file_path = _static_dir() / name
            content_type = STATIC_TYPES.get(file_path.suffix)

            if content_type is None or not file_path.is_file():
                self._json(HTTPStatus.NOT_FOUND, {"error": "Introuvable."})
                return

            body = file_path.read_bytes()

            if name == "index.html":
                body = body.replace(b"__FACTORY_TOKEN__", token.encode("ascii"))

            self._send(HTTPStatus.OK, body, content_type)

        def _dispatch(
            self,
            method: str,
            path: str,
            query: dict[str, list[str]],
            body: dict[str, Any],
        ) -> None:
            parts = [unquote(part) for part in path.split("/")[2:] if part]

            try:
                result = self._route(method, parts, query, body)
            except ServiceError as error:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
                return
            except Exception as error:  # never leak a traceback to the page
                self._json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"error": f"Erreur interne : {error.__class__.__name__}"},
                )
                return

            if result is None:
                self._json(HTTPStatus.NOT_FOUND, {"error": "Introuvable."})
                return

            self._json(HTTPStatus.OK, result)

        def _route(
            self,
            method: str,
            parts: list[str],
            query: dict[str, list[str]],
            body: dict[str, Any],
        ) -> Any:
            if parts == ["settings"]:
                if method == "GET":
                    return service.get_settings()
                return service.save_settings(body)

            if parts == ["projects"]:
                if method == "GET":
                    return {"projects": service.list_projects()}
                return service.create_project(
                    body.get("name", ""),
                    body.get("idea", ""),
                    body.get("profile", "novice"),
                )

            if len(parts) < 2 or parts[0] != "projects":
                return None

            project_id = parts[1]
            action = parts[2] if len(parts) > 2 else None

            if method == "GET":
                if action is None:
                    return service.project_view(project_id)

                if action == "file":
                    path = (query.get("path") or [""])[0]
                    return {
                        "path": path,
                        "content": service.read_file(project_id, path),
                    }

                return None

            if action == "answers":
                return service.answer_questions(
                    project_id,
                    body.get("agent", ""),
                    body.get("answers", []),
                )

            if action == "approve":
                return service.approve_step(project_id, body.get("step", ""))

            if action == "changes":
                return service.request_changes(
                    project_id,
                    body.get("agent", ""),
                    body.get("text", ""),
                )

            if action == "send-back":
                return service.send_back(project_id, body.get("source", ""))

            if action == "retry":
                return service.retry_step(project_id, body.get("agent", ""))

            if action == "run":
                service.start_run(project_id)
                return service.project_view(project_id)

            return None

    return Handler


def serve(
    service: FactoryService,
    port: int = 8765,
    open_browser: bool = True,
) -> None:
    """Serve the interface until interrupted."""

    token = secrets.token_urlsafe(32)
    port_holder = {"port": port}
    server = ThreadingHTTPServer(
        ("127.0.0.1", port),
        build_handler(service, token, port_holder),
    )
    url = f"http://127.0.0.1:{server.server_address[1]}/"

    print(f"AI Software Factory: {url}", flush=True)
    print(f"Projects folder: {service.workspace}", flush=True)
    print("Press Ctrl+C to stop.", flush=True)

    if open_browser:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
