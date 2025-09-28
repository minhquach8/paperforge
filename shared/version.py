# shared/version.py
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_DEFAULT_VERSION = "1.0.0"

def _read_bundled_version_file() -> str | None:
    """
    Đọc version từ file JSON nhúng khi build (an toàn với PyInstaller).
    """
    candidates: list[Path] = []
    # Khi chạy từ PyInstaller
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    candidates.append(base / "paperforge_build.json")
    # Khi chạy từ source
    candidates.append(Path(__file__).with_name("paperforge_build.json"))

    for p in candidates:
        try:
            if p.exists():
                data = json.loads(p.read_text(encoding="utf-8"))
                v = (data.get("version") or "").strip()
                if v:
                    return v
        except Exception:
            pass
    return None

def get_app_version() -> str:
    v = os.getenv("PAPERFORGE_VERSION")
    if v:
        return v.strip()
    v2 = _read_bundled_version_file()
    if v2:
        return v2
    return _DEFAULT_VERSION

APP_VERSION = get_app_version()
GITHUB_REPO = os.getenv("PAPERFORGE_REPO", "minhquach8/paperforge")
