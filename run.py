import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser

import auth_server


def wait_for_port(host: str, port: int, timeout: float = 120.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.4)
    return False


def start_auth_server() -> None:
    server = auth_server.build_server()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"Auth pages   -> {auth_server.AUTH_ORIGIN}")


def start_streamlit() -> subprocess.Popen:
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "app.py",
            "--server.port",
            str(auth_server.APP_PORT),
            "--server.address",
            auth_server.APP_BIND_HOST,
            "--server.headless",
            "true",
            "--browser.gatherUsageStats",
            "false",
        ],
        cwd=str(auth_server.ROOT),
    )


def main() -> int:
    start_auth_server()

    try:
        streamlit = start_streamlit()
    except FileNotFoundError:
        print("Streamlit is not installed. Run: pip install -r requirements.txt")
        return 1

    print(f"Workspace    -> {auth_server.APP_URL}")

    probe_host = "127.0.0.1" if auth_server.APP_BIND_HOST in ("0.0.0.0", "") else auth_server.APP_BIND_HOST
    if wait_for_port(probe_host, auth_server.APP_PORT):
        print(f"Opening      -> {auth_server.LOGIN_URL}")
        if os.getenv("ASTRA_OPEN_BROWSER", "1") != "0":
            webbrowser.open(auth_server.LOGIN_URL)
    else:
        print("Streamlit did not start in time. Check the log above.")

    try:
        return streamlit.wait()
    except KeyboardInterrupt:
        print("\nShutting down Astra...")
        streamlit.terminate()
        try:
            streamlit.wait(timeout=10)
        except subprocess.TimeoutExpired:
            streamlit.kill()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
