# shared/updater.py
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    # nguồn version & repo
    from shared.version import APP_VERSION, GITHUB_REPO
except Exception:
    APP_VERSION = "0.0.0"
    GITHUB_REPO = ""

USER_AGENT = "Paperforge-Updater/1.0 (+github)"

def _http_json(url: str) -> Optional[dict]:
    """GET JSON. Bắt 404 và lỗi mạng: trả None (coi như up-to-date)."""
    try:
        req = Request(url, headers={"User-Agent": USER_AGENT})
        token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        with urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except HTTPError as e:
        if e.code == 404:
            return None
        return None
    except URLError:
        return None
    except Exception:
        return None

def _normalize_ver(v: str) -> Tuple[int, ...]:
    v = (v or "").strip()
    if v.startswith("refs/tags/"):
        v = v[len("refs/tags/"):]
    if v.startswith("v"):
        v = v[1:]
    parts = []
    for p in v.split("."):
        try:
            parts.append(int("".join(ch for ch in p if ch.isdigit())))
        except Exception:
            parts.append(0)
    return tuple(parts or [0])

def _latest_release(repo: str) -> Optional[dict]:
    if not repo:
        return None
    return _http_json(f"https://api.github.com/repos/{repo}/releases/latest")

def _find_asset(assets: list[dict], substring: str) -> Optional[dict]:
    for a in assets or []:
        name = a.get("name", "")
        if substring in name:
            return a
    return None

def _download_zip_to_dir(url: str, dest_dir: Path) -> Optional[Path]:
    """Tải ZIP về memory rồi giải nén vào dest_dir/tmpextract ."""
    if not url:
        return None
    try:
        req = Request(url, headers={"User-Agent": USER_AGENT})
        token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        with urlopen(req, timeout=120) as r:
            data = r.read()
        z = zipfile.ZipFile(io.BytesIO(data))
        extract_dir = dest_dir / "extracted"
        extract_dir.mkdir(parents=True, exist_ok=True)
        z.extractall(extract_dir)
        return extract_dir
    except Exception:
        return None

def _is_windows() -> bool:
    return sys.platform.startswith("win")

def _running_exe_path() -> Path:
    # Khi đóng gói bằng PyInstaller, argv[0] là đường dẫn exe.
    return Path(sys.argv[0]).resolve()

def _app_name_from_exe(exe: Path) -> str:
    # Paperforge-Supervisor.exe -> Supervisor
    n = exe.stem
    if "-" in n:
        return n.split("-", 1)[-1]
    return n

def _portable_asset_suffix(app_name: str) -> str:
    # Tên asset theo workflow mình đã set
    # Ví dụ: Paperforge-Supervisor-Portable-win64.zip
    return f"Paperforge-{app_name}-Portable-win64.zip"

def _start_batch_and_exit(batch_path: Path, extracted_dir: Path) -> None:
    # Chạy batch (nền), đóng app hiện tại để cho phép copy đè
    # Pass đường dẫn extracted_dir làm đối số cho batch.
    try:
        os.spawnl(os.P_NOWAIT, os.environ.get("COMSPEC", "C:\\Windows\\System32\\cmd.exe"),
                  "cmd", "/c", f'"{batch_path}" "{extracted_dir}"')
    except Exception:
        # Fallback
        import subprocess
        subprocess.Popen(["cmd", "/c", str(batch_path), str(extracted_dir)])
    # Thoát app để batch có thể chép đè file đang chạy
    sys.exit(0)

def _write_update_batch(batch_path: Path, target_dir: Path, exe_name: str) -> None:
    """
    Batch file logic:
      - đợi app thoát
      - copy toàn bộ extracted/* -> target_dir (robocopy)
      - xoá thư mục tạm
      - relaunch exe
      - tự xoá
    """
    # Robocopy flags:
    # /E sao chép cả thư mục rỗng; /NFL/NDL/NJH/NJS giảm spam log
    # /R:3 /W:1 giảm retry/wait; /XO không cần vì muốn đè
    content = f"""@echo off
setlocal
set SRC=%1
set DEST="{target_dir}"
set EXE="{target_dir}\\{exe_name}"

REM đợi 1-2s cho chắc app đã thoát
ping 127.0.0.1 -n 2 >nul

REM chép đè toàn bộ
robocopy "%SRC%" %DEST% /E /NFL /NDL /NJH /NJS /R:3 /W:1 >nul

REM xoá thư mục tạm
rmdir /s /q "%SRC%" 2>nul

REM khởi động lại ứng dụng
start "" %EXE%

REM tự xoá batch
del "%~f0"
"""
    batch_path.write_text(content, encoding="utf-8")

def cleanup_legacy_appdata_if_any() -> None:
    """Dọn cơ chế cũ (đã từng copy vào %LocalAppData%\\Paperforge\\...). An toàn nếu không tồn tại."""
    if not _is_windows():
        return
    base = Path(os.getenv("LOCALAPPDATA", "")) / "Paperforge"
    try:
        if base.exists():
            # chỉ xoá subdir đã tạo, không động vào thứ khác
            for sub in ("supervisor", "student"):
                p = base / sub
                if p.exists():
                    shutil.rmtree(p, ignore_errors=True)
    except Exception:
        pass

def check_and_stage_portable_update(app_slug: str) -> Tuple[str, str]:
    """
    Kiểm tra & chuẩn bị cập nhật ngay trong thư mục đang chạy (Windows Portable).
    Trả về (status, detail) với status ∈:
      - 'up_to_date'      : không có bản mới hoặc 404/no release
      - 'staged'          : đã tải & tạo batch; app nên thoát để update
      - 'error'           : lỗi khác (chi tiết ở detail), nhưng không ném exception
    """
    if not _is_windows():
        return ("up_to_date", "non-windows: updater disabled")

    exe = _running_exe_path()
    target_dir = exe.parent
    app_name = "Supervisor" if "supervisor" in app_slug.lower() else "Student"

    # Lấy release
    rel = _latest_release(GITHUB_REPO)
    if not rel:
        return ("up_to_date", "no release / 404")

    latest_tag = rel.get("tag_name") or rel.get("name") or ""
    cur = _normalize_ver(str(APP_VERSION))
    lat = _normalize_ver(str(latest_tag))
    if lat <= cur:
        return ("up_to_date", f"current={APP_VERSION}, latest={latest_tag}")

    # Tìm asset đúng
    assets = rel.get("assets") or []
    asset = _find_asset(assets, _portable_asset_suffix(app_name))
    if not asset:
        # Không thấy asset đúng ⇒ coi như không có update
        return ("up_to_date", "asset not found for this platform")

    url = asset.get("browser_download_url")
    tmp = Path(tempfile.mkdtemp(prefix="paperforge_upd_"))
    extracted = _download_zip_to_dir(url, tmp)
    if not extracted:
        return ("error", "download/extract failed")

    # Ghi batch & chạy
    batch = tmp / "apply_update.bat"
    _write_update_batch(batch, target_dir, exe.name)
    _start_batch_and_exit(batch, extracted)
    # Không tới được đây
    return ("staged", str(batch))

# Giữ nguyên tên cũ để không vỡ import ở main.py
def download_and_stage_update(app_slug: str = "supervisor") -> Tuple[str, str]:
    """Alias cho backwards-compat."""
    return check_and_stage_portable_update(app_slug)
