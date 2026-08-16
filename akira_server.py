import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from brain import ask
from permissions import deny_all, set_confirmation_provider


set_confirmation_provider(deny_all)


HOST = "127.0.0.1"
PORT = 8765

# Локальные origins, с которых Web UI может обращаться к API.
# Произвольный сайт из интернета не входит в этот список: браузер не отдаст
# ему ответ (и заблокирует preflight), а без валидного session-токена
# запрос /ask отклоняется сервером независимо от CORS.
ALLOWED_ORIGINS = {
    f"http://{HOST}:{PORT}",
    f"http://localhost:{PORT}",
}

ALLOWED_HEADERS = "Content-Type, X-Akira-Session"
ALLOWED_METHODS = "GET, POST, OPTIONS"

MAX_SESSIONS = 200

_sessions = {}
_sessions_lock = threading.Lock()


def allowed_origin(origin):
    """Разрешает только ожидаемые локальные origins для CORS."""
    return origin in ALLOWED_ORIGINS


def issue_session():
    """Выдаёт уникальный session-токен, дающий доступ к /ask."""
    with _sessions_lock:
        while len(_sessions) >= MAX_SESSIONS:
            _sessions.pop(next(iter(_sessions)))

        token = secrets.token_urlsafe(32)
        _sessions[token] = True

    return token


def validate_session(token):
    """Проверяет, что токен был выдан этим сервером."""
    if not token:
        return False

    with _sessions_lock:
        return token in _sessions


def _session_id_from_auth(header):
    """Извлекает валидный session-токен из заголовка, иначе None."""
    token = (header or "").strip()

    if not validate_session(token):
        return None

    return token


class AkiraHandler(BaseHTTPRequestHandler):

    def send_cors(self):
        """Добавляет CORS-заголовки только для разрешённых локальных origins."""
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
        index_file = Path("web/index.html")

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

        response = json.dumps(
            {"session_id": token},
            ensure_ascii=False,
        ).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response)))
        self.send_cors()
        self.end_headers()

        self.wfile.write(response)

    def do_GET(self):
        if self.path in ["/", "/index.html"]:
            self._serve_index()
            return

        if self.path == "/session":
            self._serve_session()
            return

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
            data = self.rfile.read(length)

            payload = json.loads(data.decode("utf-8"))
            message = payload.get("message", "").strip()

            if not message:
                self.send_error(400, "Пустое сообщение")
                return

            answer = ask(message, session_id=session_id)

            response = json.dumps(
                {"answer": answer},
                ensure_ascii=False,
            ).encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(response)))
            self.send_cors()
            self.end_headers()

            self.wfile.write(response)

        except Exception as error:
            response = json.dumps(
                {"error": str(error)},
                ensure_ascii=False,
            ).encode("utf-8")

            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(response)))
            self.send_cors()
            self.end_headers()

            self.wfile.write(response)

    def log_message(self, format, *args):
        print("[Akira Server]", format % args)


def create_server(host=HOST, port=PORT):
    return HTTPServer((host, port), AkiraHandler)


if __name__ == "__main__":
    print(f"Акира Server запущен на http://{HOST}:{PORT}")
    create_server().serve_forever()