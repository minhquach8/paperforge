# shared/updater.py
from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# ─────────────────────────────────────────────────────────────────────────────
# Build info (fallback nếu thiếu)
# ─────────────────────────────────────────────────────────────────────────────
try:
    from shared.version import APP_VERSION, GITHUB_REPO
except Exception:
    APP_VERSION = "0.0.0"
    GITHUB_REPO = ""

USER_AGENT = "Paperforge-Updater/1.0 (+github)"
# minisign -P public key (base64)
UPDATER_PUBKEY = "RWQLy6cizwaFR9iOagKScwuIBIfG5aM/BzGTEz7cFmb/SiJ0tQEKn/a7"


# ─────────────────────────────────────────────────────────────────────────────
# HTTP helpers
# ─────────────────────────────────────────────────────────────────────────────
def _auth_request(url: str) -> Request:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    return req


def _http_json(url: str) -> Optional[dict]:
    """GET JSON. Bắt 404 và lỗi mạng: trả None (coi như up-to-date)."""
    try:
        with urlopen(_auth_request(url), timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except HTTPError as e:
        if e.code == 404:
            return None
        return None
    except URLError:
        return None
    except Exception:
        return None


def _http_bytes(url: str) -> Optional[bytes]:
    """GET raw bytes with auth header."""
    if not url:
        return None
    try:
        with urlopen(_auth_request(url), timeout=180) as r:
            return r.read()
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Version, releases, assets
# ─────────────────────────────────────────────────────────────────────────────
def _normalize_ver(v: str) -> Tuple[int, ...]:
    v = (v or "").strip()
    if v.startswith("refs/tags/"):
        v = v[len("refs/tags/") :]
    if v.startswith("v"):
        v = v[1:]
    parts: list[int] = []
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


def _find_asset(assets: list[dict], name_substring: str) -> Optional[dict]:
    if not assets:
        return None
    sub = (name_substring or "").lower()
    for a in assets:
        name = (a.get("name") or "").lower()
        if sub in name:
            return a
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Platform / paths
# ─────────────────────────────────────────────────────────────────────────────
def _is_windows() -> bool:
    return sys.platform.startswith("win")


def _running_exe_path() -> Path:
    # Khi đóng gói bằng PyInstaller, argv[0] là đường dẫn exe.
    return Path(sys.argv[0]).resolve()


def _portable_asset_name(app_name: str) -> str:
    # Ví dụ: Paperforge-Supervisor-Portable-win64.zip
    return f"Paperforge-{app_name}-Portable-win64.zip"


def _app_name_from_slug(slug: str) -> str:
    # "supervisor" -> "Supervisor", "student" -> "Student"
    s = (slug or "").strip().lower()
    return "Supervisor" if "super" in s else "Student"


# ─────────────────────────────────────────────────────────────────────────────
# minisign verify (tuỳ chọn, nhưng nếu có .minisig thì sẽ bắt buộc)
# ─────────────────────────────────────────────────────────────────────────────
def _locate_minisign_exe() -> Optional[Path]:
    # 1) Bundle bên trong app (PyInstaller)
    try:
        if hasattr(sys, "_MEIPASS"):
            cand = Path(sys._MEIPASS) / "vendor" / "minisign" / "windows" / "minisign.exe"  # type: ignore[attr-defined]
            if cand.exists():
                return cand
    except Exception:
        pass
    # 2) PATH (dev/mac/linux)
    exe = shutil.which("minisign")
    return Path(exe) if exe else None


def verify_minisign(zip_path: Path, sig_path: Path) -> bool:
    exe = _locate_minisign_exe()
    if not exe:
        # Không có minisign ⇒ coi là không verify được
        return False
    cmd = [str(exe), "-V", "-P", UPDATER_PUBKEY, "-m", str(zip_path), "-x", str(sig_path)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0


# ─────────────────────────────────────────────────────────────────────────────
# Download + extract + (optional) verify
# ─────────────────────────────────────────────────────────────────────────────
def _download_zip_to_dir(url: str, dest_dir: Path, sig_url: Optional[str]) -> Optional[Path]:
    """Tải ZIP (và chữ ký nếu có) rồi giải nén vào dest_dir/extracted ."""
    data = _http_bytes(url)
    if not data:
        return None

    # Nếu có chữ ký ⇒ bắt verify (bảo mật update)
    if sig_url:
        sig = _http_bytes(sig_url)
        if not sig:
            return None
        tmp_zip = dest_dir / "pkg.zip"
        tmp_sig = dest_dir / "pkg.zip.minisig"
        tmp_zip.write_bytes(data)
        tmp_sig.write_bytes(sig)
        ok = verify_minisign(tmp_zip, tmp_sig)
        if not ok:
            return None
        # verified ⇒ tiếp tục extract từ tmp_zip để tiết kiệm RAM
        zpath = tmp_zip
        with zipfile.ZipFile(str(zpath), "r") as zf:
            extract_dir = dest_dir / "extracted"
            extract_dir.mkdir(parents=True, exist_ok=True)
            zf.extractall(extract_dir)
            return extract_dir

    # Không có chữ ký ⇒ extract trực tiếp (tương thích các release cũ)
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        extract_dir = dest_dir / "extracted"
        extract_dir.mkdir(parents=True, exist_ok=True)
        zf.extractall(extract_dir)
        return extract_dir
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Batch apply (Windows portable)
# ─────────────────────────────────────────────────────────────────────────────
def _write_update_batch(batch_path: Path, target_dir: Path, exe_name: str) -> None:
    """
    Batch file:
      - đợi app thoát
      - robocopy extracted/* -> target_dir
      - xoá thư mục tạm
      - relaunch exe
      - tự xoá
    """
    content = f"""@echo off
setlocal
set SRC=%1
set DEST="{target_dir}"
set EXE="{target_dir}\\{exe_name}"

REM Đợi ~1s để chắc app đã thoát
ping 127.0.0.1 -n 2 >nul

REM Sao chép đè toàn bộ (yên lặng)
robocopy "%SRC%" %DEST% /E /NFL /NDL /NJH /NJS /R:2 /W:1 >nul

REM Xoá thư mục tạm
rmdir /s /q "%SRC%" 2>nul
rmdir /s /q "{target_dir}\\..\\_updtmp" 2>nul

REM Khởi động lại ứng dụng
start "" %EXE%

REM Tự xoá batch
del "%~f0"
"""
    batch_path.write_text(content, encoding="utf-8")


def _start_batch_and_exit(batch_path: Path, extracted_dir: Path) -> None:
    # Chạy batch (nền), pass thư mục extracted làm argv1.
    try:
        cmdexe = os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe")
        os.spawnl(os.P_NOWAIT, cmdexe, "cmd", "/c", f'"{batch_path}" "{extracted_dir}"')
    except Exception:
        subprocess.Popen(["cmd", "/c", str(batch_path), str(extracted_dir)], close_fds=True)
    # Thoát app để batch có thể copy đè file đang chạy
    sys.exit(0)


# ─────────────────────────────────────────────────────────────────────────────
# Public APIs
# ─────────────────────────────────────────────────────────────────────────────
def cleanup_legacy_appdata_if_any() -> None:
    """Dọn cơ chế update cũ trong %LocalAppData%\\Paperforge\\... (an toàn nếu không tồn tại)."""
    if not _is_windows():
        return
    base = Path(os.getenv("LOCALAPPDATA", "")) / "Paperforge"
    try:
        if base.exists():
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
      - 'error'           : lỗi khác (detail mô tả)
    """
    if not _is_windows():
        return ("up_to_date", "non-windows: updater disabled")

    exe = _running_exe_path()
    target_dir = exe.parent  # update **in-place** (không dùng AppData)
    app_name = _app_name_from_slug(app_slug)

    rel = _latest_release(GITHUB_REPO)
    if not rel:
        return ("up_to_date", "no release / 404")

    latest_tag = rel.get("tag_name") or rel.get("name") or ""
    cur = _normalize_ver(str(APP_VERSION))
    lat = _normalize_ver(str(latest_tag))
    if lat <= cur:
        return ("up_to_date", f"current={APP_VERSION}, latest={latest_tag}")

    assets = rel.get("assets") or []
    zip_name = _portable_asset_name(app_name)
    asset = _find_asset(assets, zip_name)
    if not asset:
        # Không thấy asset đúng ⇒ coi như không có update cho nền tảng này
        return ("up_to_date", "asset not found for this platform")

    zip_url = asset.get("browser_download_url") or ""

    # Nếu có chữ ký .minisig thì bắt buộc verify
    sig_asset = _find_asset(assets, zip_name + ".minisig")
    sig_url = sig_asset.get("browser_download_url") if sig_asset else None

    tmp_root = Path(tempfile.mkdtemp(prefix="paperforge_upd_"))
    # tạo một tầng _updtmp/ để batch có thể dọn dẹp
    updtmp = target_dir.parent / "_updtmp"
    try:
        updtmp.mkdir(exist_ok=True)
    except Exception:
        pass

    extracted = _download_zip_to_dir(zip_url, tmp_root, sig_url)
    if not extracted:
        if sig_asset:
            return ("error", "signature verify failed or download error")
        return ("error", "download/extract failed")

    batch = updtmp / "apply_update.bat"
    _write_update_batch(batch, target_dir, exe.name)

    # Chuyển extracted vào _updtmp để batch dễ dọn
    staged_src = updtmp / "extracted"
    try:
        if staged_src.exists():
            shutil.rmtree(staged_src, ignore_errors=True)
        shutil.move(str(extracted), str(staged_src))
    except Exception:
        # Fallback: copy
        shutil.copytree(extracted, staged_src, dirs_exist_ok=True)

    _start_batch_and_exit(batch, staged_src)
    return ("staged", str(batch))  # không tới được đây thực tế


# Giữ tên cũ để không vỡ import ở các main; hỗ trợ cả signature cũ lẫn mới
def download_and_stage_update(*args, **kwargs) -> Tuple[str, str]:
    """
    Compatibility wrapper:
      - New style: download_and_stage_update("supervisor" | "student")
      - Old style: download_and_stage_update(GITHUB_REPO, "Supervisor", APP_VERSION, app_id="supervisor")
    Trả về (status, detail) như check_and_stage_portable_update.
    """
    # New style
    if len(args) == 1 and isinstance(args[0], str) and "/" not in args[0]:
        return check_and_stage_portable_update(args[0])

    # Old style
    if args and isinstance(args[0], str) and "/" in args[0]:
        # repo, app_keyword, version, [app_id=...]
        app_id = kwargs.get("app_id")
        if not app_id and len(args) >= 4:
            app_id = args[3]
        if not app_id:
            # dự đoán theo app_keyword
            kw = (args[1] if len(args) >= 2 else "") or ""
            app_id = "supervisor" if "super" in kw.lower() else "student"
        return check_and_stage_portable_update(str(app_id))

    # Fallback (assume supervisor)
    slug = kwargs.get("app_id") or "supervisor"
    return check_and_stage_portable_update(str(slug))
