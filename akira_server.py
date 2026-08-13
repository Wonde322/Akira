from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import json

from brain import ask


HOST = "127.0.0.1"
PORT = 8765


class AkiraHandler(BaseHTTPRequestHandler):

    def send_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_cors()
        self.end_headers()


    def do_GET(self):
        if self.path not in ["/", "/index.html"]:
            self.send_error(404)
            return

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

    def do_POST(self):
        if self.path != "/ask":
            self.send_error(404)
            return

        try:
            length = int(self.headers.get("Content-Length", 0))
            data = self.rfile.read(length)

            payload = json.loads(data.decode("utf-8"))
            message = payload.get("message", "").strip()

            if not message:
                self.send_error(400, "Пустое сообщение")
                return

            answer = ask(message)

            response = json.dumps(
                {
                    "answer": answer
                },
                ensure_ascii=False
            ).encode("utf-8")

            self.send_response(200)
            self.send_header(
                "Content-Type",
                "application/json; charset=utf-8"
            )
            self.send_header(
                "Content-Length",
                str(len(response))
            )
            self.end_headers()

            self.wfile.write(response)

        except Exception as error:
            response = json.dumps(
                {
                    "error": str(error)
                },
                ensure_ascii=False
            ).encode("utf-8")

            self.send_response(500)
            self.send_header(
                "Content-Type",
                "application/json; charset=utf-8"
            )
            self.send_header(
                "Content-Length",
                str(len(response))
            )
            self.end_headers()

            self.wfile.write(response)

    def log_message(self, format, *args):
        print("[Akira Server]", format % args)


print(f"Акира Server запущен на http://{HOST}:{PORT}")

server = HTTPServer(
    (HOST, PORT),
    AkiraHandler
)

server.serve_forever()
