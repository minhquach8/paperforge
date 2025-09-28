# shared/updater.py
from __future__ import annotations

import json
import os
import sys
import webbrowser
from dataclasses import dataclass
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from shared.version import APP_VERSION, GITHUB_REPO

USER_AGENT = "Paperforge-Updater/1"

@dataclass
class ReleaseInfo:
    tag: str
    html_url: str
    assets: list[dict]

def _http_get_json(url: str, token: Optional[str]) -> tuple[Optional[dict], Optional[str]]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github+json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urlopen(Request(url, headers=headers), timeout=15) as r:
            return json.loads(r.read().decode("utf-8")), None
    except HTTPError as e:
        # BẮT 404: coi như không có update, đừng hiện lỗi
        if e.code == 404:
            return None, "404"
        return None, f"http_{e.code}"
    except URLError:
        return None, "net"
    except Exception:
        return None, "err"

def _parse_repo(spec: str) -> tuple[str, str]:
    parts = spec.strip().split("/")
    if len(parts) != 2:
        raise ValueError("GITHUB_REPO must be '<owner>/<repo>'")
    return parts[0], parts[1]

def _norm(v: str) -> tuple[int, ...]:
    v = v.strip().lstrip("vV")
    out = []
    for seg in v.split("."):
        try: out.append(int(seg))
        except: out.append(0)
    return tuple(out) or (0,)

def _platform_tag() -> str:
    if sys.platform.startswith("win"): return "win"
    if sys.platform == "darwin": return "mac"
    return "other"

def _pick_asset(assets: list[dict], app_kind: str) -> Optional[dict]:
    name_like = app_kind.lower()      # 'student' / 'supervisor'
    plat = _platform_tag()
    def score(a: dict) -> int:
        n = (a.get("name") or "").lower()
        s = 0
        if name_like in n: s += 10
        if "portable" in n: s += 5
        if plat == "win" and ("win" in n or "windows" in n): s += 3
        if plat == "mac" and ("mac" in n or "darwin" in n): s += 3
        if n.endswith(".zip"): s += 1
        return s
    assets_sorted = sorted(assets, key=score, reverse=True)
    return assets_sorted[0] if assets_sorted and score(assets_sorted[0]) > 0 else None

def fetch_latest_release() -> tuple[Optional[ReleaseInfo], Optional[str]]:
    owner, repo = _parse_repo(GITHUB_REPO)
    token = os.getenv("PAPERFORGE_GH_TOKEN") or None
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    data, err = _http_get_json(url, token)
    if err == "404":
        return None, None  # im lặng: chưa có release
    if err or not data:
        return None, err or "empty"
    return ReleaseInfo(
        tag=(data.get("tag_name") or "").strip(),
        html_url=(data.get("html_url") or "").strip(),
        assets=data.get("assets") or [],
    ), None

def check_update_info(app_kind: str) -> tuple[bool, Optional[str], Optional[str]]:
    """
    -> (has_update, latest_version, download_or_release_url)
    """
    rel, _ = fetch_latest_release()
    if not rel or not rel.tag:
        return (False, None, None)
    if _norm(rel.tag) <= _norm(APP_VERSION):
        return (False, rel.tag, None)
    asset = _pick_asset(rel.assets, app_kind)
    if asset and asset.get("browser_download_url"):
        return (True, rel.tag, asset["browser_download_url"])
    return (True, rel.tag, rel.html_url or None)

def check_for_updates_safely(app_kind: str, status_cb=None, on_update_url=None) -> None:
    has, ver, url = check_update_info(app_kind)
    if not has:
        if status_cb:
            status_cb("Up-to-date" if ver else "No updates")
        return
    if status_cb:
        status_cb(f"Update {ver} available")
    if url:
        if on_update_url:
            on_update_url(url)
        else:
            webbrowser.open(url)
