import json
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".ENV")

AUTH_HOST = os.getenv("ASTRA_AUTH_HOST", "localhost")
AUTH_BIND_HOST = os.getenv("ASTRA_AUTH_BIND", "127.0.0.1")
AUTH_PORT = int(os.getenv("ASTRA_AUTH_PORT", "8001"))
APP_BIND_HOST = os.getenv("ASTRA_APP_BIND", "127.0.0.1")
APP_PORT = int(os.getenv("ASTRA_APP_PORT", "8501"))

AUTH_ORIGIN = os.getenv("ASTRA_AUTH_URL", f"http://{AUTH_HOST}:{AUTH_PORT}").rstrip("/")
APP_URL = os.getenv("ASTRA_APP_URL", f"http://{AUTH_HOST}:{APP_PORT}").rstrip("/")
LOGIN_URL = f"{AUTH_ORIGIN}/html/login.html"
SIGNUP_URL = f"{AUTH_ORIGIN}/html/signup.html"
LOGOUT_URL = f"{AUTH_ORIGIN}/html/login.html?signedout=1"

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("SUPERBASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPERNASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    raise RuntimeError("Supabase URL and anon key must be set in .ENV")


class AuthHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        kwargs["directory"] = str(ROOT)
        super().__init__(*args, **kwargs)

    def do_GET(self):
        path = self.path.split("?", 1)[0]

        if path == "/auth-config.js":
            config = (
                f"window.ASTRA_SUPABASE_URL = {json.dumps(SUPABASE_URL)};\n"
                f"window.ASTRA_SUPABASE_ANON_KEY = {json.dumps(SUPABASE_ANON_KEY)};\n"
                f"window.ASTRA_APP_URL = {json.dumps(APP_URL)};\n"
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(config)))
            self.end_headers()
            self.wfile.write(config)
            return

        if path in ("/", "/index.html"):
            self.send_response(302)
            self.send_header("Location", "/html/login.html")
            self.end_headers()
            return

        super().do_GET()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def build_server() -> ThreadingHTTPServer:
    return ThreadingHTTPServer((AUTH_BIND_HOST, AUTH_PORT), AuthHandler)


if __name__ == "__main__":
    server = build_server()
    print(f"Astra auth pages: {LOGIN_URL}")
    server.serve_forever()
