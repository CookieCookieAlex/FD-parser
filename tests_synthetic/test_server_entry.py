"""Regression test for fd_reader.server_entry -- the standalone launcher's
child-process Streamlit entry point (see launcher.py's module docstring
for why this is a separate process, not an in-process thread: Streamlit's
bootstrap.run() installs a SIGTERM handler that requires the main thread,
which conflicts with Tkinter also needing the main thread in the same
process).

This module deliberately has zero tkinter dependency so it's testable
even on a machine without Tkinter installed (confirmed necessary during
development -- this Linux dev environment lacks the system Tkinter
library, which blocked testing launcher.py directly).
"""
import socket
import subprocess
import sys
import time
import urllib.request

from fd_reader.server_entry import __file__ as SERVER_ENTRY_FILE


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(port: int, timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            time.sleep(0.3)
    return False


def test_server_entry_starts_and_serves_real_page():
    """End-to-end: launch fd_reader/server_entry.py as a real child
    process (same invocation shape launcher.py uses for the frozen .exe's
    --run-server branch), confirm it opens the port and serves an actual
    HTTP response, then confirm it shuts down cleanly on terminate()."""
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, SERVER_ENTRY_FILE, str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        assert _wait_for_port(port), "server did not open its port in time"

        time.sleep(1)  # let the app finish its first render pass
        resp = urllib.request.urlopen(f"http://localhost:{port}", timeout=5)
        assert resp.status == 200
        body = resp.read().decode()
        assert len(body) > 1000  # real Streamlit HTML shell, not an error page
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
