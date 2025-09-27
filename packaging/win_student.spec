# -*- mode: python ; coding: utf-8 -*-
import os
from pathlib import Path

# Robust project root resolution: __file__ may not exist on some PyInstaller invocations.
try:
    THIS = Path(__file__).resolve()
    PROJECT_ROOT = THIS.parent.parent
except Exception:
    PROJECT_ROOT = Path.cwd()

block_cipher = None

# Entrypoint
app_entry = str(PROJECT_ROOT / "apps" / "student_app" / "main.py")

# Include assets (optional) + bundled Tectonic for Windows
datas = [
    # copy whole assets dir if you use images/icons in the app:
    (str(PROJECT_ROOT / "assets"), "assets"),
    # bundle tectonic.exe into the same relative path the app expects:
    (str(PROJECT_ROOT / "vendor" / "tectonic" / "windows-x86_64" / "tectonic.exe"),
     "vendor/tectonic/windows-x86_64"),
]

binaries = []
hiddenimports = [
    "PySide6.QtWidgets",
    "PySide6.QtGui",
    "PySide6.QtCore",
]

a = Analysis(
    [app_entry],
    pathex=[str(PROJECT_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name="Paperforge-Student",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # windowed app
    disable_windowed_traceback=False,
    # icon=str(PROJECT_ROOT / "assets" / "app.ico"),  # nếu có icon
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Paperforge-Student",
)
