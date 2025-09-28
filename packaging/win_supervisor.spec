# -*- mode: python ; coding: utf-8 -*-
import os
from pathlib import Path

try:
    THIS = Path(__file__).resolve()
    PROJECT_ROOT = THIS.parent.parent
except Exception:
    PROJECT_ROOT = Path.cwd()

block_cipher = None

app_entry = str(PROJECT_ROOT / "apps" / "supervisor_app" / "main.py")

datas = [
    (str(PROJECT_ROOT / "assets"), "assets"),
    (str(PROJECT_ROOT / "vendor" / "tectonic" / "windows-x86_64" / "tectonic.exe"),
     "vendor/tectonic/windows-x86_64"),
     ('shared/paperforge_build.json', '.') ,
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
    name="Paperforge-Supervisor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # windowed
    disable_windowed_traceback=False,
    # icon=str(PROJECT_ROOT / "assets" / "app.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Paperforge-Supervisor",
)
