# shared/latex/tectonic_runtime.py
from __future__ import annotations

import os
import platform
import sys
from pathlib import Path


def _is_frozen() -> bool:
    return hasattr(sys, "_MEIPASS")

def _base_dir() -> Path:
    # Khi freeze bằng PyInstaller, dữ liệu sẽ bung vào sys._MEIPASS
    if _is_frozen():
        return Path(sys._MEIPASS)
    # Dev mode: .../shared/latex/tectonic_runtime.py -> project root = parents[2]
    return Path(__file__).resolve().parents[2]

def get_vendor_dir() -> Path:
    return _base_dir() / "vendor" / "tectonic"

def _platform_subdir() -> str:
    if sys.platform.startswith("win"):
        return "windows-x86_64"
    if sys.platform == "darwin":
        arch = platform.machine().lower()
        return "darwin-arm64" if "arm" in arch else "darwin-x86_64"
    # (Không ship Linux trong dự án này)
    return "unknown-linux"

def get_tectonic_path() -> Path:
    exe = "tectonic.exe" if sys.platform.startswith("win") else "tectonic"
    p = get_vendor_dir() / _platform_subdir() / exe
    return p

def get_cache_dir() -> Path:
    # Cache riêng cho Paperforge để portable không đòi TeX tree ngoài
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        d = base / "Paperforge" / "Tectonic"
    elif sys.platform == "darwin":
        d = Path.home() / "Library" / "Caches" / "Paperforge" / "Tectonic"
    else:
        d = Path.home() / ".cache" / "paperforge" / "tectonic"
    d.mkdir(parents=True, exist_ok=True)
    return d

def _ensure_executable(p: Path) -> None:
    if not sys.platform.startswith("win") and p.exists():
        try:
            p.chmod(0o755)
        except Exception:
            pass

def tectonic_command_env() -> tuple[str, dict]:
    """
    Trả về (đường_dẫn_tectonic, biến_môi_trường) đã set sẵn cache.
    Dùng cho subprocess.run([...], env=env).
    """
    exe = get_tectonic_path()
    _ensure_executable(exe)

    # Fallback: nếu không tìm thấy trong vendor, thử PATH hệ thống
    if not exe.exists():
        exe = Path("tectonic")  # để subprocess tự tìm theo PATH

    env = os.environ.copy()
    env.setdefault("TECTONIC_CACHE_DIR", str(get_cache_dir()))
    # Một số môi trường cần TEXMFHOME/TEXMFVAR riêng (không bắt buộc với Tectonic, nhưng vô hại)
    env.setdefault("TEXMFHOME", str(get_cache_dir() / "texmfhome"))
    env.setdefault("TEXMFVAR", str(get_cache_dir() / "texmfvar"))
    return (str(exe), env)
