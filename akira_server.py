import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from brain import ask
from config import PROJECT_ROOT
from permissions import deny_all, set_confirmation_provider

HOST = "127.0.0.1"
PORT = 8765
MAX_REQUEST_BYTES = 1_000_000
ALLOWED_ORIGINS = {f"http://{HOST}:{PORT}", f"http://localhost:{PORT}"}
ALLOWED_HEADERS = "Content-Type, X-Akira-Session"
ALLOWED_METHODS = "GET, POST, OPTIONS"
MAX_SESSIONS = 200

_sessions = {}
_sessions_lock = threading.Lock()


def allowed_origin(origin):
    return origin in ALLOWED_ORIGINS


def issue_session():
    with _sessions_lock:
        while len(_sessions) >= MAX_SESSIONS:
            _sessions.pop(next(iter(_sessions)))
        token = secrets.token_urlsafe(32)
        _sessions[token] = True
    return token


def validate_session(token):
    if not token:
        return False
    with _sessions_lock:
        return token in _sessions


def _session_id_from_auth(header):
    token = (header or "").strip()
    return token if validate_session(token) else None


def _index_file():
    """Prefer an explicitly supplied local web root, then the project asset."""
    local = Path.cwd() / "web" / "index.html"
    return local if local.exists() else PROJECT_ROOT / "web" / "index.html"


class AkiraHandler(BaseHTTPRequestHandler):
    def send_cors(self):
        origin = self.headers.get("Origin")
        if not allowed_origin(origin):
            return
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", ALLOWED_METHODS)
        self.send_header("Access-Control-Allow-Headers", ALLOWED_HEADERS)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_cors()
        self.end_headers()

    def _serve_index(self):
        index_file = _index_file()
        if not index_file.exists():
            self.send_error(404, "index.html not found")
            return
        content = index_file.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _serve_session(self):
        token = issue_session()
        response = json.dumps({"session_id": token}, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response)))
        self.send_cors()
        self.end_headers()
        self.wfile.write(response)

    def do_GET(self):
        if self.path in ["/", "/index.html"]:
            self._serve_index()
        elif self.path == "/session":
            self._serve_session()
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/ask":
            self.send_error(404)
            return
        session_id = _session_id_from_auth(self.headers.get("X-Akira-Session"))
        if session_id is None:
            self.send_error(401, "Unauthorized")
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            self.send_error(400, "Invalid Content-Length")
            return
        if length < 1:
            self.send_error(400, "Пустое сообщение")
            return
        if length > MAX_REQUEST_BYTES:
            self.send_error(413, "Request body too large")
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.send_error(400, "Invalid JSON")
            return
        if not isinstance(payload, dict):
            self.send_error(400, "JSON payload must be an object")
            return
        message = payload.get("message")
        if not isinstance(message, str) or not message.strip():
            self.send_error(400, "Пустое сообщение")
            return
        try:
            answer = ask(message.strip(), session_id=session_id)
        except Exception:
            self.send_error(500, "Internal server error")
            return
        response = json.dumps({"answer": answer}, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response)))
        self.send_cors()
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, format, *args):
        print("[Akira Server]", format % args)


def create_server(host=HOST, port=PORT):
    set_confirmation_provider(deny_all)
    return HTTPServer((host, port), AkiraHandler)


if __name__ == "__main__":
    print(f"Акира Server запущен на http://{HOST}:{PORT}")
    create_server().serve_forever()
