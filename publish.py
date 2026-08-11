import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from queue import Empty, Queue

ROOT = Path(__file__).resolve().parent
PROXY_PORT = int(os.getenv("ASTRA_PROXY_PORT", "8080"))
QUICK_TUNNEL_PATTERN = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")

CADDY_CANDIDATES = [
    Path(os.getenv("LOCALAPPDATA", "")) / "Microsoft/WinGet/Packages"
    / "CaddyServer.Caddy_Microsoft.Winget.Source_8wekyb3d8bbwe/caddy.exe",
]
CLOUDFLARED_CANDIDATES = [
    Path(os.getenv("ProgramFiles(x86)", "")) / "cloudflared/cloudflared.exe",
    Path(os.getenv("ProgramFiles", "")) / "cloudflared/cloudflared.exe",
]


def locate(name: str, candidates: list) -> str:
    found = shutil.which(name)
    if found:
        return found
    for candidate in candidates:
        if candidate and candidate.is_file():
            return str(candidate)
    raise SystemExit(
        f"{name} was not found. Install it with winget, then run this again."
    )


def wait_for_port(host: str, port: int, timeout: float = 120.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.4)
    return False


def start_caddy(caddy: str) -> subprocess.Popen:
    return subprocess.Popen(
        [caddy, "run", "--config", str(ROOT / "Caddyfile"), "--adapter", "caddyfile"],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def start_tunnel(cloudflared: str) -> tuple:
    process = subprocess.Popen(
        [
            cloudflared,
            "tunnel",
            "--no-autoupdate",
            "--url",
            f"http://127.0.0.1:{PROXY_PORT}",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    found = Queue()

    def watch():
        for line in process.stdout:
            match = QUICK_TUNNEL_PATTERN.search(line)
            if match:
                found.put(match.group(0))

    threading.Thread(target=watch, daemon=True).start()

    try:
        return process, found.get(timeout=60)
    except Empty:
        process.terminate()
        raise SystemExit("Cloudflare did not hand out a tunnel URL within 60 seconds.")


def start_streamlit(app_port: int) -> subprocess.Popen:
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "app.py",
            "--server.port",
            str(app_port),
            "--server.address",
            "127.0.0.1",
            "--server.headless",
            "true",
            "--server.enableCORS",
            "false",
            "--browser.gatherUsageStats",
            "false",
        ],
        cwd=str(ROOT),
    )


def main() -> int:
    caddy = locate("caddy", CADDY_CANDIDATES)
    cloudflared = locate("cloudflared", CLOUDFLARED_CANDIDATES)

    print("Starting local reverse proxy...")
    caddy_process = start_caddy(caddy)
    if not wait_for_port("127.0.0.1", PROXY_PORT, timeout=20):
        caddy_process.terminate()
        return print(f"Caddy did not open port {PROXY_PORT}.") or 1

    print("Opening Cloudflare quick tunnel...")
    tunnel_process, public_url = start_tunnel(cloudflared)

    os.environ["ASTRA_AUTH_URL"] = public_url
    os.environ["ASTRA_APP_URL"] = public_url
    os.environ["ASTRA_OPEN_BROWSER"] = "0"

    import auth_server

    server = auth_server.build_server()
    threading.Thread(target=server.serve_forever, daemon=True).start()

    streamlit_process = start_streamlit(auth_server.APP_PORT)
    wait_for_port("127.0.0.1", auth_server.APP_PORT)

    print()
    print("=" * 68)
    print(f"  Astra is live at   {public_url}")
    print(f"  Sample meeting     {public_url}/?demo=1")
    print(f"  Sign in            {public_url}/html/login.html")
    print("=" * 68)
    print("  This URL is temporary and changes every time you restart.")
    print("  For Google sign-in, add it to Supabase redirect URLs first.")
    print("  Press Ctrl+C to take it offline.")
    print()

    try:
        streamlit_process.wait()
    except KeyboardInterrupt:
        print("\nTaking Astra offline...")
    finally:
        for process in (streamlit_process, tunnel_process, caddy_process):
            if process.poll() is None:
                process.terminate()
        for process in (streamlit_process, tunnel_process, caddy_process):
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
