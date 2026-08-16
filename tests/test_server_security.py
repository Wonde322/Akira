import json
import pathlib
import threading
import urllib.error
import urllib.request

import pytest


@pytest.fixture
def server(monkeypatch):
    import akira_server

    monkeypatch.setattr(
        akira_server,
        "ask",
        lambda message, session_id=None: f"ok:{session_id}",
    )

    httpd = akira_server.create_server(port=0)
    port = httpd.server_address[1]

    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    yield akira_server, port

    httpd.shutdown()
    httpd.server_close()


def _request(port, method, path, data=None, headers=None):
    url = f"http://127.0.0.1:{port}{path}"
    body = json.dumps(data).encode() if data is not None else None

    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers=headers or {},
    )

    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read()


def test_issue_and_validate_session_isolation(server):
    akira_server, _ = server

    token = akira_server.issue_session()

    assert akira_server.validate_session(token) is True
    assert akira_server.validate_session("not-issued") is False
    assert akira_server.validate_session("") is False
    assert akira_server.validate_session(None) is False


def test_allowed_origin_only_for_expected_local_sources(server):
    akira_server, _ = server

    assert akira_server.allowed_origin("http://127.0.0.1:8765") is True
    assert akira_server.allowed_origin("http://localhost:8765") is True
    assert akira_server.allowed_origin("https://evil.example") is False
    assert akira_server.allowed_origin("http://127.0.0.1:9999") is False
    assert akira_server.allowed_origin(None) is False


def test_get_session_issues_valid_token(server):
    _, port = server

    status, _, body = _request(port, "GET", "/session")

    assert status == 200

    token = json.loads(body)["session_id"]
    assert token
    assert server[0].validate_session(token) is True


def test_ask_without_token_is_rejected(server):
    _, port = server

    status, _, _ = _request(port, "POST", "/ask", data={"message": "hi"})

    assert status == 401


def test_ask_with_invalid_token_is_rejected(server):
    _, port = server

    status, _, _ = _request(
        port,
        "POST",
        "/ask",
        data={"message": "hi"},
        headers={"X-Akira-Session": "forged-token"},
    )

    assert status == 401


def test_ask_with_valid_token_is_accepted_and_isolated(server):
    _, port = server

    token_status, _, token_body = _request(port, "GET", "/session")
    assert token_status == 200

    token = json.loads(token_body)["session_id"]

    status, _, body = _request(
        port,
        "POST",
        "/ask",
        data={"message": "hi"},
        headers={"X-Akira-Session": token},
    )

    assert status == 200
    assert json.loads(body)["answer"] == f"ok:{token}"


def test_index_page_is_served(server, tmp_path, monkeypatch):
    import pathlib

    web_dir = tmp_path / "web"
    web_dir.mkdir()
    (web_dir / "index.html").write_text("AKIRA UI", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    _, port = server

    status, headers, body = _request(port, "GET", "/")

    assert status == 200
    assert "text/html" in headers.get("Content-Type", "")
    assert body == b"AKIRA UI"


def test_web_ui_uses_server_session_token():
    source = pathlib.Path(__file__).resolve().parents[1] / "web" / "index.html"
    content = source.read_text(encoding="utf-8")

    assert "X-Akira-Session" in content
    assert "/session" in content
    assert "crypto.randomUUID" not in content


def test_disallowed_origin_gets_no_cors_headers(server):
    _, port = server

    status, headers, _ = _request(
        port,
        "OPTIONS",
        "/ask",
        headers={"Origin": "https://evil.example"},
    )

    assert status == 204
    assert "Access-Control-Allow-Origin" not in headers


def test_allowed_origin_gets_cors_headers(server):
    _, port = server

    status, headers, _ = _request(
        port,
        "OPTIONS",
        "/ask",
        headers={"Origin": "http://127.0.0.1:8765"},
    )

    assert status == 204
    assert headers.get("Access-Control-Allow-Origin") == "http://127.0.0.1:8765"
    assert "X-Akira-Session" in headers.get("Access-Control-Allow-Headers", "")


def test_evil_origin_cannot_reach_ask_even_with_cors_bypass(server):
    """Даже с честным Origin произвольный сайт не имеет токена — 401."""
    _, port = server

    status, headers, _ = _request(
        port,
        "POST",
        "/ask",
        data={"message": "hi"},
        headers={"Origin": "https://evil.example"},
    )

    assert status == 401
    assert "Access-Control-Allow-Origin" not in headers