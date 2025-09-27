# -*- mode: python ; coding: utf-8 -*-

# Deterministic, portable onedir build for Supervisor app (Windows).
# Ensures dist/Paperforge-Supervisor exists for CI zip step.

import os
from pathlib import Path

block_cipher = None
project_root = Path(__file__).resolve().parents[1]

a = Analysis(
    ['apps/supervisor_app/main.py'],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        ('vendor/tectonic/windows-x86_64/tectonic.exe', 'tectonic/windows-x86_64'),
        ('assets/*', 'assets'),
    ],
    hiddenimports=[
        'shiboken6',
        'PySide6',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name='Paperforge-Supervisor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Paperforge-Supervisor',
)
