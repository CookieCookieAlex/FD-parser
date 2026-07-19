"""Standalone desktop launcher for the Streamlit GUI.

This is the entry point PyInstaller packages into a single Windows .exe.
Double-clicking the .exe: starts the Streamlit server as a CHILD PROCESS
(itself, re-invoked with an internal flag -- see below), opens it in the
default browser, and shows a small always-on-top window with a "Stop"
button -- closing that window (or clicking Stop) kills the server, so
there's no need to find/close a terminal window.

Not used for local development -- for that, run
`streamlit run fd_reader/app.py` directly (see HOW_TO_RUN.md). This
launcher exists purely so the packaged .exe has something to double-click
that doesn't leave a bare terminal window as the only way to stop the
server.

HOW THE CHILD PROCESS WORKS (`--run-server` internal flag -> delegates to
fd_reader/server_entry.py), and why it's built this way -- both points
below were real bugs found by actually running the packaged .exe on
Windows, not guessed up front:

1. `sys.executable` in a frozen PyInstaller build IS this .exe -- there's
   no separate python.exe bundled alongside it. So the child process has
   to be `[sys.executable, "--run-server", port]` (re-invoking itself),
   not `[sys.executable, "-m", "streamlit", "run", ...]` (which would
   treat this exe as if it were a python.exe with a -m flag, which it
   isn't). `--run-server` tells main() to skip the Tkinter/subprocess-
   launching path entirely and just run the Streamlit server directly --
   otherwise every launch would recursively spawn another full launcher,
   which is exactly the infinite-window-loop bug seen on first test.
2. The server genuinely needs a separate child PROCESS, not an in-process
   background thread: Streamlit's own `bootstrap.run()` unconditionally
   calls `signal.signal(signal.SIGTERM, ...)` to install a shutdown
   handler, which only works on a process's MAIN thread -- but Tkinter's
   event loop also needs the main thread. Running Streamlit in a
   background thread inside the same process as Tkinter crashes with
   "signal only works in main thread of the main interpreter" (confirmed
   by testing this exact scenario locally). A real child process
   sidesteps this entirely: Streamlit owns its own process's main thread,
   Tkinter owns this one.
3. The actual server-launching code lives in fd_reader/server_entry.py,
   not here, so it has zero Tkinter dependency and can be tested on a
   machine without Tkinter installed at all (this mattered during
   development -- see SESSION_HISTORY.md).
"""
from __future__ import annotations

import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser

_RUN_SERVER_FLAG = "--run-server"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_server(port: int, timeout: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            time.sleep(0.3)
    return False


def _launch_server_subprocess(port: int) -> subprocess.Popen:
    if getattr(sys, "frozen", False):
        # The frozen .exe re-invokes itself -- see module docstring point 1
        # for why this must be the .exe with an internal flag, not
        # `[exe, "-m", "streamlit", ...]`.
        cmd = [sys.executable, _RUN_SERVER_FLAG, str(port)]
    else:
        # Dev/unfrozen: invoke server_entry.py directly as its own script
        # (not through launcher.py) so the child process never imports
        # tkinter at all -- keeps this path testable on a machine without
        # Tkinter installed (see fd_reader/server_entry.py's docstring).
        import fd_reader.server_entry as _server_entry

        cmd = [sys.executable, _server_entry.__file__, str(port)]

    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]

    return subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )


def _main_launcher() -> None:
    port = _free_port()
    url = f"http://localhost:{port}"
    process = _launch_server_subprocess(port)

    root = tk.Tk()
    root.title("Guest x Yelp Cross-Check")
    root.geometry("360x140")
    root.attributes("-topmost", True)

    status_label = tk.Label(root, text="Starting server...", font=("Segoe UI", 11))
    status_label.pack(pady=(20, 10))

    def stop() -> None:
        if process.poll() is None:
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


def main() -> None:
    if len(sys.argv) >= 2 and sys.argv[1] == _RUN_SERVER_FLAG:
        from fd_reader.server_entry import run_server

        run_server(int(sys.argv[2]))
    else:
        _main_launcher()


if __name__ == "__main__":
    main()
