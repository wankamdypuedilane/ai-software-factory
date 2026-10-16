import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from ai_factory.providers import MockProvider
from ai_factory.web.server import TOKEN_HEADER, build_handler
from ai_factory.web.service import FactoryService


TOKEN = "test-token"


@pytest.fixture
def base_url(tmp_path: Path):
    service = FactoryService(
        workspace=tmp_path / "projects",
        provider_factory=lambda config: MockProvider(),
        settings_path=tmp_path / "settings.json",
        run_in_background=False,
    )
    service.save_settings({"provider": "mock"})
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        build_handler(service, TOKEN, {"port": 0}),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def _request(url, method="GET", body=None, token=TOKEN, host=None):
    headers = {"Content-Type": "application/json"}

    if token is not None:
        headers[TOKEN_HEADER] = token

    if host is not None:
        headers["Host"] = host

    request = urllib.request.Request(
        url,
        method=method,
        data=None if body is None else json.dumps(body).encode(),
        headers=headers,
    )

    try:
        with urllib.request.urlopen(request) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def test_page_embeds_the_session_token(base_url) -> None:
    status, body = _request(base_url + "/", token=None)

    assert status == 200
    assert TOKEN.encode() in body
    assert b"__FACTORY_TOKEN__" not in body


def test_api_refuses_requests_without_the_token(base_url) -> None:
    assert _request(base_url + "/api/projects", token=None)[0] == 403
    assert _request(base_url + "/api/projects", token="wrong")[0] == 403
    assert _request(
        base_url + "/api/projects",
        method="POST",
        body={"name": "X", "idea": "Une idée assez longue."},
        token=None,
    )[0] == 403


def test_non_local_host_is_refused(base_url) -> None:
    assert _request(base_url + "/", token=None, host="evil.example")[0] == 403
    assert _request(base_url + "/api/projects", host="evil.example")[0] == 403


def test_static_paths_cannot_escape(base_url) -> None:
    assert _request(base_url + "/app.js", token=None)[0] == 200
    assert _request(base_url + "/../service.py", token=None)[0] == 404
    assert _request(base_url + "/service.py", token=None)[0] == 404


def test_create_and_approve_through_http(base_url) -> None:
    status, body = _request(
        base_url + "/api/projects",
        method="POST",
        body={"name": "Http App", "idea": "Une idée assez longue.", "profile": "novice"},
    )

    view = json.loads(body)
    assert status == 200
    assert view["pending"]["kind"] == "review"

    status, body = _request(
        base_url + "/api/projects/http-app/approve",
        method="POST",
        body={"step": "product"},
    )

    assert status == 200
    assert json.loads(body)["pending"]["agent"] == "ux_ui"


def test_service_errors_are_returned_as_messages(base_url) -> None:
    status, body = _request(
        base_url + "/api/projects",
        method="POST",
        body={"name": "", "idea": "x"},
    )

    assert status == 400
    assert "nom" in json.loads(body)["error"]
