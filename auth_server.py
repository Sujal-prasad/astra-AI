import json
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".ENV")

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("SUPERBASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPERNASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    raise RuntimeError("Supabase URL and anon key must be set in .ENV")


class AuthHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/auth-config.js":
            config = (
                f"window.ASTRA_SUPABASE_URL = {json.dumps(SUPABASE_URL)};\n"
                f"window.ASTRA_SUPABASE_ANON_KEY = {json.dumps(SUPABASE_ANON_KEY)};\n"
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(config)))
            self.end_headers()
            self.wfile.write(config)
            return

        super().do_GET()


if __name__ == "__main__":
    os.chdir(ROOT)
    server = ThreadingHTTPServer(("localhost", 8001), AuthHandler)
    print("Astra auth pages: http://localhost:8001/html/login.html")
    server.serve_forever()
