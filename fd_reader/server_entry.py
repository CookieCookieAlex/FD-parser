"""Child-process entry point for the standalone launcher's Streamlit
server. Deliberately has NO Tkinter dependency (unlike launcher.py, which
owns the Stop-window UI) -- this runs in a separate child process from
the Tkinter window (see launcher.py's module docstring for why: Streamlit's
bootstrap.run() installs a SIGTERM handler that only works on a process's
main thread, which conflicts with Tkinter also needing the main thread of
its own process). Splitting this out also means it's testable on a machine
with no Tkinter installed at all, since importing this module never
touches tkinter.
"""
from __future__ import annotations

import sys
from pathlib import Path


def app_path() -> Path:
    # When frozen by PyInstaller, app.py is bundled alongside the .exe
    # (see fd_reader.spec's datas entry) rather than importable as a
    # package -- run it by path either way so dev and frozen behave the
    # same.
    if getattr(sys, "frozen", False):
        base_dir = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base_dir = Path(__file__).resolve().parent.parent
    return base_dir / "fd_reader" / "app.py"


def run_server(port: int) -> None:
    """Runs on this process's own main thread, exactly like a real
    `streamlit run` invocation would -- equivalent to:
        streamlit run <app_path> --server.port <port>
            --server.headless true --browser.gatherUsageStats false
            --global.developmentMode false

    The last flag is required in the frozen .exe specifically: Streamlit
    auto-detects "development mode" by checking whether
    "site-packages" appears in streamlit/config.py's own file path (true
    for a normal `pip install`, false otherwise) -- but a PyInstaller
    build unpacks everything into a temp _MEIPASS directory with no
    site-packages in the path at all, so that heuristic wrongly concludes
    "this is a dev checkout" and turns development mode on. With it on,
    Streamlit raises "server.port does not work when
    global.developmentMode is true" and refuses to start -- confirmed by
    running the actual packaged .exe on Windows, not guessed up front.
    Explicitly forcing it off here overrides the bad auto-detection.
    """
    from streamlit.web import cli as stcli

    sys.argv = [
        "streamlit", "run", str(app_path()),
        "--server.port", str(port),
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
        "--global.developmentMode", "false",
    ]
    sys.exit(stcli.main())


if __name__ == "__main__":
    run_server(int(sys.argv[1]))
