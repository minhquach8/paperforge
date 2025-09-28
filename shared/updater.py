# shared/updater.py
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple
from urllib.request import Request, urlopen

USER_AGENT = "PaperforgeUpdater/1.0 (+https://github.com)"


@dataclass
class ReleaseAsset:
    name: str
    download_url: str
    size: int


@dataclass
class ReleaseInfo:
    tag: str
    notes: str
    assets: list[ReleaseAsset]


def _version_tuple(v: str) -> Tuple[int, ...]:
    v = v.strip().lstrip("vV")
    parts = []
    for p in v.replace("-", ".").split("."):
        try:
            parts.append(int(p))
        except ValueError:
            break
    return tuple(parts) or (0,)


def _http_json(url: str, token: Optional[str] = None) -> dict:
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _download(url: str, dest: Path, token: Optional[str] = None) -> None:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(1024 * 256)
            if not chunk:
                break
            f.write(chunk)


def get_latest_release(repo: str, token: Optional[str] = None) -> ReleaseInfo:
    api = f"https://api.github.com/repos/{repo}/releases/latest"
    data = _http_json(api, token=token)
    assets = [
        ReleaseAsset(
            name=a.get("name", ""),
            download_url=a.get("browser_download_url", ""),
            size=a.get("size", 0),
        )
        for a in (data.get("assets") or [])
    ]
    return ReleaseInfo(tag=data.get("tag_name", ""), notes=data.get("body", "") or "", assets=assets)


def pick_asset_for_platform(ri: ReleaseInfo, app_keyword: str) -> Optional[ReleaseAsset]:
    """Chọn asset phù hợp OS (ưu tiên Windows portable .zip)."""
    name_kw = app_keyword.lower()
    os_name = "win" if sys.platform.startswith("win") else ("mac" if sys.platform == "darwin" else "linux")

    def match(a: ReleaseAsset) -> bool:
        n = a.name.lower()
        if name_kw not in n:
            return False
        if os_name == "win":
            return n.endswith(".zip") and ("win" in n or "windows" in n)
        if os_name == "mac":
            return any(n.endswith(ext) for ext in (".zip", ".tar.gz", ".dmg")) and any(k in n for k in ("darwin", "mac", "osx"))
        # linux (nếu cần sau này)
        return any(n.endswith(ext) for ext in (".AppImage", ".tar.gz", ".zip"))

    # ưu tiên portable trước (tên có "portable")
    portable = [a for a in ri.assets if match(a) and "portable" in a.name.lower()]
    if portable:
        return portable[0]
    # fallback: cái đầu tiên phù hợp
    for a in ri.assets:
        if match(a):
            return a
    return None


def install_zip_windows(zip_path: Path, app_id: str, tag: str) -> Path:
    """Giải nén zip vào %LOCALAPPDATA%/Paperforge/<app_id>/<tag>/ và trả về đường dẫn exe mới."""
    base = Path(os.getenv("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    target = base / "Paperforge" / app_id / tag.lstrip("vV")
    target.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(target)

    # Tìm exe có chữ Supervisor/Student
    exe = None
    for p in target.rglob("*.exe"):
        if app_id.lower() in p.name.lower():
            exe = p
            break
    if not exe:
        # fallback: lấy *.exe đầu tiên
        for p in target.rglob("*.exe"):
            exe = p
            break
    if not exe:
        raise RuntimeError("Cannot locate .exe inside extracted update.")
    return exe


def check_update(repo: str, app_keyword: str, current_version: str, token: Optional[str] = None) -> Tuple[bool, ReleaseInfo, Optional[ReleaseAsset]]:
    ri = get_latest_release(repo, token=token)
    latest = _version_tuple(ri.tag)
    current = _version_tuple(current_version)
    if latest <= current or not ri.assets:
        return False, ri, None
    asset = pick_asset_for_platform(ri, app_keyword)
    return (asset is not None), ri, asset


def download_and_stage_update(repo: str, app_keyword: str, current_version: str, app_id: str) -> Optional[Path]:
    """Tải & bung bản mới; trả về đường dẫn exe/app mới, hoặc None nếu không có."""
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")  # optional
    has, ri, asset = check_update(repo, app_keyword, current_version, token=token)
    if not has or not asset:
        return None

    tmp = Path(tempfile.gettempdir()) / f"{asset.name}"
    _download(asset.download_url, tmp, token=token)

    if sys.platform.startswith("win"):
        return install_zip_windows(tmp, app_id=app_id, tag=ri.tag)

    # macOS: nếu asset là .zip chứa app bundle → giải nén ~/Library/Application Support/Paperforge/<app_id>/<tag>/
    if sys.platform == "darwin":
        # MVP: chỉ tải file và mở thư mục cho người dùng (hoặc bạn có thể thêm code giải nén .zip ở đây)
        return tmp  # caller sẽ mở Finder/hiển thị hướng dẫn

    # linux: tương tự mac — để sau
    return tmp
