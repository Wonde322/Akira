"""Explicit, cancellable Spotify PKCE authorization; safe to import."""
import base64
import hashlib
import json
import secrets
import ssl
import time
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import certifi
from execution_context import raise_if_execution_cancelled
from spotify_control import CLIENT_ID

REDIRECT_URI = "http://127.0.0.1:8766/callback"
SCOPES = "user-read-playback-state user-modify-playback-state"
AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"


def authorize(timeout=120):
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(24)
    result = {}

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            valid = parsed.path == "/callback" and secrets.compare_digest(query.get("state", [""])[0], state)
            if valid and ("code" in query or "error" in query):
                key = "code" if "code" in query else "error"
                result[key] = query[key][0]
                body = "Ответ получен. Вернитесь в окно Акиры.".encode()
                status = 200
            else:
                body = b"Invalid OAuth callback"
                status = 400
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    params = {"client_id": CLIENT_ID, "response_type": "code", "redirect_uri": REDIRECT_URI,
              "scope": SCOPES, "code_challenge_method": "S256", "code_challenge": challenge, "state": state}
    raise_if_execution_cancelled()
    with HTTPServer(("127.0.0.1", 8766), CallbackHandler) as server:
        server.timeout = 0.2
        if not webbrowser.open(AUTH_URL + "?" + urlencode(params)):
            raise RuntimeError("Не удалось открыть браузер для подключения Spotify.")
        deadline = time.monotonic() + timeout
        while not result:
            raise_if_execution_cancelled()
            if time.monotonic() >= deadline:
                raise RuntimeError("Время подключения Spotify истекло. Повторите запрос.")
            server.handle_request()
    if "error" in result:
        raise RuntimeError("Spotify не подключён: " + result["error"])
    raise_if_execution_cancelled()
    data = urlencode({"client_id": CLIENT_ID, "grant_type": "authorization_code", "code": result["code"],
                      "redirect_uri": REDIRECT_URI, "code_verifier": verifier}).encode()
    request = urllib.request.Request(TOKEN_URL, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(request, context=ssl.create_default_context(cafile=certifi.where()), timeout=15) as response:
        token = json.loads(response.read())
    raise_if_execution_cancelled()
    from spotify_control import save_token
    save_token(token)
    return token


if __name__ == "__main__":
    authorize()
    print("Spotify подключён.")
