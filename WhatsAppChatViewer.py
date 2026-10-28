
import os
import sys
import time
import socket
import subprocess
import traceback
from pathlib import Path

APP_NAME = "WhatsApp Forensic Chat Viewer"
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8501
SERVER_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"

LOG_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
LOG_DIR = LOG_DIR / "WhatsAppForensicChatViewer"
LOG_FILE = LOG_DIR / "launcher.log"


def log(message):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
            f"{message}\n"
        )
        f.flush()


def get_bundle_directory():
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def run_streamlit_server():
    log("Child process: starting Streamlit server.")
    app_file = get_bundle_directory() / "app.py"
    log(f"app.py path: {app_file}")
    log(f"app.py exists: {app_file.exists()}")

    if not app_file.exists():
        raise FileNotFoundError(f"Could not find app.py: {app_file}")

    os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"

    from streamlit.web import cli as stcli

    sys.argv = [
        "streamlit",
        "run",
        str(app_file),
        "--global.developmentMode=false",
        "--server.headless=true",
        f"--server.address={SERVER_HOST}",
        f"--server.port={SERVER_PORT}",
        "--server.fileWatcherType=none",
        "--browser.gatherUsageStats=false",
    ]

    log("Calling Streamlit CLI.")
    stcli.main()


def wait_for_server(process, timeout=90):
    start = time.time()
    log("Waiting for Streamlit to become available.")

    while time.time() - start < timeout:
        if process.poll() is not None:
            raise RuntimeError(
                f"Streamlit child process exited with code "
                f"{process.returncode}. See log: {LOG_FILE}"
            )

        try:
            with socket.create_connection(
                (SERVER_HOST, SERVER_PORT), timeout=1
            ):
                log("Streamlit server is responding.")
                return
        except OSError:
            time.sleep(0.5)

    raise TimeoutError("Streamlit did not start within 90 seconds.")


def main():
    log(f"Launcher started. Frozen={getattr(sys, 'frozen', False)}")
    log(f"Executable: {sys.executable}")
    log(f"Arguments: {sys.argv}")

    if "--streamlit-server" in sys.argv:
        run_streamlit_server()
        return

    import webview
    log("pywebview imported successfully.")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        if sock.connect_ex((SERVER_HOST, SERVER_PORT)) == 0:
            raise RuntimeError(
                f"Port {SERVER_PORT} is already in use. "
                "Close the other viewer instance and try again."
            )

    if getattr(sys, "frozen", False):
        command = [sys.executable, "--streamlit-server"]
    else:
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--streamlit-server",
        ]

    log(f"Starting child process: {command}")

    child_log = open(LOG_FILE, "a", encoding="utf-8")
    server_process = subprocess.Popen(
        command,
        cwd=str(get_bundle_directory()),
        env={
            **os.environ,
            "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false",
        },
        stdout=child_log,
        stderr=subprocess.STDOUT,
    )

    try:
        log(f"Child process PID: {server_process.pid}")
        wait_for_server(server_process)

        log("Creating desktop window.")
        webview.create_window(
            APP_NAME,
            SERVER_URL,
            width=1280,
            height=850,
            min_size=(900, 600),
            text_select=True,
        )

        log("Starting Edge Chromium GUI.")
        webview.start(gui="edgechromium", debug=False)
        log("Desktop window closed.")

    finally:
        log("Stopping Streamlit child process.")
        if server_process.poll() is None:
            server_process.terminate()
            try:
                server_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server_process.kill()
                server_process.wait()

        child_log.close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        error = traceback.format_exc()
        log("FATAL ERROR:\n" + error)
        print(error)
        print(f"\nDiagnostic log: {LOG_FILE}")
        input("\nPress Enter to exit...")
