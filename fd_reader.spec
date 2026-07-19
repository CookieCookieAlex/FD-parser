# PyInstaller spec for the standalone Windows launcher.
#
# Build (on Windows, with this project's requirements + pyinstaller
# installed):
#   pyinstaller fd_reader.spec
#
# Output: dist/GuestYelpCheck/GuestYelpCheck.exe (a folder build, not
# --onefile -- Streamlit's static assets are large enough that a single
# self-extracting exe would be slow to start every launch; the folder can
# still be zipped up and sent as one file).
#
# Streamlit does a lot of dynamic module/resource discovery that
# PyInstaller's static analysis can't see, so its own hook coverage
# (via the streamlit package's PyInstaller hook, picked up automatically
# by newer PyInstaller/streamlit versions) plus these extra collects are
# what make the frozen app actually run instead of failing at import time.
from PyInstaller.utils.hooks import collect_all, collect_data_files

datas = []
binaries = []
hiddenimports = []

for pkg in ("streamlit", "pdfplumber", "pandas", "openpyxl", "rapidfuzz"):
    pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hiddenimports

# The Streamlit app script itself + this project's package, bundled as
# data so fd_reader/server_entry.py can find fd_reader/app.py as a real
# file at runtime (via sys._MEIPASS when frozen) to hand to Streamlit's
# CLI -- see server_entry.py's app_path().
datas += [("fd_reader", "fd_reader")]

a = Analysis(
    ["launcher.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="GuestYelpCheck",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # no bare terminal window -- launcher.py's Tk window is the UI
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="GuestYelpCheck",
)
