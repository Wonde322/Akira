import ssl
import certifi
import base64
import hashlib
import json
import os
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

CLIENT_ID = "71886dbe05744e1c9ea56d7ffd1eec1c"
REDIRECT_URI = "http://127.0.0.1:8766/callback"

SCOPES = "user-read-playback-state user-modify-playback-state"

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"

SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

VERIFIER = base64.urlsafe_b64encode(
    secrets.token_bytes(32)
).rstrip(b"=").decode()

CHALLENGE = base64.urlsafe_b64encode(
    hashlib.sha256(VERIFIER.encode()).digest()
).rstrip(b"=").decode()

result = {}


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)

        if "code" in query:
            result["code"] = query["code"][0]

            body = """
            <html>
            <body style="font-family: sans-serif; text-align:center; padding:60px">
            <h1>Spotify подключён</h1>
            <p>Можешь закрыть эту вкладку.</p>
            </body>
            </html>
            """.encode()

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif "error" in query:
            result["error"] = query["error"][0]

    def log_message(self, *args):
        pass


server = HTTPServer(("127.0.0.1", 8766), CallbackHandler)

threading.Thread(
    target=server.serve_forever,
    daemon=True
).start()

params = {
    "client_id": CLIENT_ID,
    "response_type": "code",
    "redirect_uri": REDIRECT_URI,
    "scope": SCOPES,
    "code_challenge_method": "S256",
    "code_challenge": CHALLENGE,
}

url = AUTH_URL + "?" + urlencode(params)

print("Открываю Spotify для авторизации...")
webbrowser.open(url)

while "code" not in result and "error" not in result:
    time.sleep(0.2)

server.shutdown()

if "error" in result:
    raise SystemExit("Spotify OAuth ошибка: " + result["error"])

code = result["code"]

import urllib.request

data = urlencode({
    "client_id": CLIENT_ID,
    "grant_type": "authorization_code",
    "code": code,
    "redirect_uri": REDIRECT_URI,
    "code_verifier": VERIFIER,
}).encode()

request = urllib.request.Request(
    TOKEN_URL,
    data=data,
    headers={
        "Content-Type": "application/x-www-form-urlencoded"
    },
)

with urllib.request.urlopen(request, context=SSL_CONTEXT) as response:
    token = json.loads(response.read())

token_path = os.path.expanduser("~/Akira/spotify_token.json")

with open(token_path, "w") as f:
    json.dump(token, f, indent=2)

print()
print("Spotify успешно подключён.")
print("Токен сохранён локально в:", token_path)
print("Можно закрыть это окно.")
