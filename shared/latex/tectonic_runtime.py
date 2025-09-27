# British English comments.
import platform
import shutil
import sys
from pathlib import Path


def _base_dir_for_assets() -> Path:
    # When frozen (PyInstaller), assets live next to the executable (one-folder),
    # or under a temp _MEIPASS dir (one-file). Prefer those locations.
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        return base
    # Dev mode: project root = two levels up from this file
    return Path(__file__).resolve().parents[2]

def get_tectonic_path() -> Path | None:
    sysname = platform.system().lower()
    arch = platform.machine().lower()

    # 1) Look inside bundled assets (PyInstaller)
    base = _base_dir_for_assets()
    # note: in PyInstaller we place it under "tectonic/<platform>/..."
    if sysname == "windows":
        cand = base / "tectonic" / "windows-x86_64" / "tectonic.exe"
    elif sysname == "darwin" and arch in ("arm64", "aarch64"):
        cand = base / "tectonic" / "darwin-arm64" / "tectonic"
    elif sysname == "darwin":
        cand = base / "tectonic" / "darwin-x86_64" / "tectonic"
    else:
        cand = None
    if cand and cand.exists():
        return cand

    # 2) Dev fallback: vendor/tectonic in repo
    dev_root = Path(__file__).resolve().parents[2] / "vendor" / "tectonic"
    if sysname == "windows":
        cand = dev_root / "windows-x86_64" / "tectonic.exe"
    elif sysname == "darwin" and arch in ("arm64", "aarch64"):
        cand = dev_root / "darwin-arm64" / "tectonic"
    elif sysname == "darwin":
        cand = dev_root / "darwin-x86_64" / "tectonic"
    if cand and cand.exists():
        return cand

    # 3) PATH fallback
    exe = "tectonic.exe" if sysname == "windows" else "tectonic"
    p = shutil.which(exe)
    return Path(p) if p else None
