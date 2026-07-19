"""Standalone desktop launcher for the Streamlit GUI.

This is the entry point PyInstaller packages into a single Windows .exe.
Double-clicking the .exe: starts the Streamlit server on a local port,
opens it in the default browser, and shows a small always-on-top window
with a "Stop" button -- closing that window (or clicking Stop) kills the
server, so there's no need to find/close a terminal window.

Not used for local development -- for that, run
`streamlit run fd_reader/app.py` directly (see HOW_TO_RUN.md). This
launcher exists purely so the packaged .exe has something to double-click
that doesn't leave a bare terminal window as the only way to stop the
server.
"""
from __future__ import annotations

import socket
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_server(port: int, timeout: float = 30.0) -> bool:
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            time.sleep(0.3)
    return False


def main() -> None:
    # When frozen by PyInstaller, app.py is bundled alongside this script
    # (see fd_reader.spec's datas entry) rather than importable as a
    # package -- run it by path either way so dev and frozen behave the
    # same.
    if getattr(sys, "frozen", False):
        base_dir = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base_dir = Path(__file__).resolve().parent
    app_path = base_dir / "fd_reader" / "app.py"

    port = _free_port()

    streamlit_cmd = [
        sys.executable,
        "-m", "streamlit", "run", str(app_path),
        "--server.port", str(port),
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
    ]
    process = subprocess.Popen(
        streamlit_cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    url = f"http://localhost:{port}"

    root = tk.Tk()
    root.title("Guest x Yelp Cross-Check")
    root.geometry("360x140")
    root.attributes("-topmost", True)

    status_label = tk.Label(root, text="Starting server...", font=("Segoe UI", 11))
    status_label.pack(pady=(20, 10))

    def stop() -> None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        root.destroy()

    stop_button = tk.Button(root, text="Stop", command=stop, width=12, bg="#FFC7CE")
    stop_button.pack(pady=10)

    root.protocol("WM_DELETE_WINDOW", stop)

    def wait_and_open() -> None:
        if _wait_for_server(port):
            status_label.config(text=f"Running at {url}\n(this window stays open)")
            webbrowser.open(url)
        else:
            status_label.config(text="Server failed to start.")

    threading.Thread(target=wait_and_open, daemon=True).start()

    root.mainloop()

    if process.poll() is None:
        process.terminate()


if __name__ == "__main__":
    main()
