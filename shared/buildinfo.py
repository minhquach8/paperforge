# shared/buildinfo.py
from __future__ import annotations

import json
import sys
from pathlib import Path

from shared.version import APP_VERSION, GITHUB_REPO


def _exe_dir() -> Path:
    try:
        return Path(sys.executable).resolve().parent
    except Exception:
        return Path.cwd()

def get_display_version() -> str:
    """
    Prefer the stamped build number (paperforge_build.json), fall back to APP_VERSION.
    Works in both PyInstaller (data collected to exe dir) and dev mode.
    """
    candidates = [
        _exe_dir() / "paperforge_build.json",                          # bundled by .spec to "."
        Path(__file__).resolve().parent / "paperforge_build.json",     # dev fallback
    ]
    for p in candidates:
        try:
            if p.exists():
                v = json.loads(p.read_text(encoding="utf-8")).get("version", "").strip()
                if v:
                    return v
        except Exception:
            pass
    return APP_VERSION

def get_repo() -> str:
    return GITHUB_REPO
