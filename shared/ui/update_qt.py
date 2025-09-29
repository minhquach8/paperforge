# shared/ui/update_qt.py
from __future__ import annotations

import json as _json
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog


# ── version helpers ──────────────────────────────────────────────────────
def _vtuple(s: str) -> tuple[int, ...]:
    return tuple(int(x) for x in s.split(".") if x.isdigit())

def is_newer(cur: str, latest: str) -> bool:
    try:
        return _vtuple(cur) < _vtuple(latest)
    except Exception:
        return True  # nếu parse lỗi, cứ cho phép update

def _sanitize_tag(tag: str) -> str:
    # 'v1.2.3-beta.1+meta' -> '1.2.3-beta.1'
    return (tag or "").strip().lstrip("v").split("+", 1)[0]

def fetch_latest_version(repo: str, *, allow_prerelease: bool = True, timeout_sec: float = 10.0) -> Optional[str]:
    """
    Lấy version mới nhất từ GitHub:
      1) /releases/latest (stable)
      2) /releases (lọc draft; có thể gồm prerelease nếu allow_prerelease=True)
      3) /tags (fallback)
    Trả về 'x.y.z' hoặc None nếu không lấy được.
    """
    UA = {"User-Agent": "Paperforge-Updater"}

    # 1) stable latest
    try:
        url = f"https://api.github.com/repos/{repo}/releases/latest"
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout_sec) as resp:
            data = _json.loads(resp.read().decode("utf-8"))
        tag = _sanitize_tag(data.get("tag_name") or "")
        if tag:
            return tag
    except Exception:
        pass

    # 2) list releases (optionally include pre-releases)
    try:
        url = f"https://api.github.com/repos/{repo}/releases?per_page=20"
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout_sec) as resp:
            arr = _json.loads(resp.read().decode("utf-8"))
        cands = []
        for r in arr or []:
            if r.get("draft"):
                continue
            if (not allow_prerelease) and r.get("prerelease"):
                continue
            t = _sanitize_tag(r.get("tag_name") or "")
            if t:
                cands.append(t)
        if cands:
            cands.sort(key=_vtuple)
            return cands[-1]
    except Exception:
        pass

    # 3) tags fallback
    try:
        url = f"https://api.github.com/repos/{repo}/tags?per_page=20"
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout_sec) as resp:
            arr = _json.loads(resp.read().decode("utf-8"))
        tags = [_sanitize_tag(t.get("name") or "") for t in arr or []]
        tags = [t for t in tags if any(ch.isdigit() for ch in t)]
        if tags:
            tags.sort(key=_vtuple)
            return tags[-1]
    except Exception:
        pass

    return None


# ── worker ───────────────────────────────────────────────────────────────
class UpdateWorker(QThread):
    done = Signal(object)     # path (str/Path) của file đã tải xong/staged
    up_to_date = Signal()
    error = Signal(str)

    def __init__(self, *, app_id: str, repo: str, current_version: str, app_keyword: str, parent=None):
        super().__init__(parent)
        self.app_id = app_id
        self.repo = repo
        self.current_version = current_version
        self.app_keyword = app_keyword

    def run(self):
        from shared.updater import download_and_stage_update
        try:
            # API cũ
            try:
                res = download_and_stage_update(self.repo, self.app_keyword, self.current_version, app_id=self.app_id)
            except TypeError:
                # API mới
                res = download_and_stage_update(self.app_id)

            if isinstance(res, tuple):
                status, detail = res
                if status == "up_to_date":
                    self.up_to_date.emit(); return
                if status == "staged":
                    self.done.emit(detail); return
                self.error.emit(str(detail)); return

            if isinstance(res, (str, Path)) and res:
                self.done.emit(res); return

            self.up_to_date.emit()

        except Exception as e:
            msg = str(e)
            if "404" in msg or "Not Found" in msg:
                self.up_to_date.emit()
            else:
                self.error.emit(msg)


# ── apply on Windows (portable in-place swap) ────────────────────────────
def apply_inplace_update(parent, staged_path: Path) -> None:
    try:
        if sys.platform.startswith("win"):
            exe = Path(sys.executable).resolve()
            exe_dir = exe.parent
            staged_path = Path(staged_path).resolve()
            if not staged_path.exists():
                QMessageBox.warning(parent, "Update", f"Downloaded file missing:\n{staged_path}")
                return

            new_copy = exe_dir / (exe.name + ".new")
            shutil.copy2(staged_path, new_copy)

            swap = exe_dir / "_swap_update.cmd"
            swap.write_text(
                rf"""@echo off
setlocal
set TARGET="{exe}"
set NEW="{new_copy}"
set OLD="{exe}.old"
:wait
ping 127.0.0.1 -n 2 >nul
move /y %TARGET% %OLD% >nul 2>&1
if errorlevel 1 goto wait
move /y %NEW% %TARGET% >nul 2>&1
del /f /q %OLD% >nul 2>&1
start "" "%TARGET%"
exit
""",
                encoding="utf-8",
            )

            try:
                if "AppData" in str(staged_path):
                    shutil.rmtree(staged_path.parent, ignore_errors=True)
            except Exception:
                pass

            from subprocess import Popen
            Popen(["cmd", "/c", str(swap)], close_fds=True)
            QApplication.quit()
        else:
            QMessageBox.information(
                parent,
                "Update downloaded",
                "An update has been downloaded. Please replace your app with the new one.",
            )
            p = Path(staged_path)
            if p.exists():
                from subprocess import run
                if sys.platform == "darwin":
                    run(["open", str(p.parent)], check=False)
                else:
                    run(["xdg-open", str(p.parent)], check=False)
    except Exception as e:
        QMessageBox.warning(parent, "Update", f"Failed to apply update:\n{e}")


# ── helpers ──────────────────────────────────────────────────────────────
def _open_releases_page(repo: str):
    QDesktopServices.openUrl(QUrl(f"https://github.com/{repo}/releases/latest"))


# ── one-shot UI flow ─────────────────────────────────────────────────────
def check_for_updates(
    parent,
    *,
    app_id: str,
    repo: str,
    current_version: str,
    app_keyword: str,
    allow_prerelease: bool = True,
    watchdog_ms: int = 8 * 60_000  # 8 phút cho file zip lớn
) -> None:
    ans = QMessageBox.question(
        parent,
        "Check for updates",
        f"Current version: v{current_version}\nCheck online for a new version now?",
        QMessageBox.Yes | QMessageBox.No,
    )
    if ans != QMessageBox.Yes:
        return

    latest = fetch_latest_version(repo, allow_prerelease=allow_prerelease, timeout_sec=10)
    if not latest:
        QMessageBox.information(parent, "Updates", "Couldn't reach update server. Please try again later.")
        return
    if not is_newer(current_version, latest):
        QMessageBox.information(parent, "Updates", f"No update found.\nCurrent: v{current_version}\nLatest online: v{latest}")
        return

    # Progress dialog có nút mở Releases page
    dlg = QProgressDialog("Downloading update…", "Open Releases page…", 0, 0, parent)
    dlg.setWindowModality(Qt.ApplicationModal)
    dlg.setMinimumDuration(0)
    dlg.setWindowTitle("Updates")
    dlg.show()

    w = UpdateWorker(app_id=app_id, repo=repo, current_version=current_version, app_keyword=app_keyword, parent=parent)

    def _cleanup():
        try:
            dlg.close()
        except Exception:
            pass

    # Cancel = mở trang Releases
    def _on_cancel():
        try:
            if w.isRunning():
                w.terminate()
        except Exception:
            pass
        _cleanup()
        _open_releases_page(repo)

    dlg.canceled.connect(_on_cancel)

    # Watchdog dài hơi
    watchdog = QTimer(parent)
    watchdog.setSingleShot(True)

    def _on_timeout():
        try:
            if w.isRunning():
                w.terminate()
        finally:
            _cleanup()
            r = QMessageBox.question(
                parent,
                "Download taking too long",
                "The download seems to be taking too long.\n"
                "Do you want to open the Releases page and download manually?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if r == QMessageBox.Yes:
                _open_releases_page(repo)

    watchdog.timeout.connect(_on_timeout)
    watchdog.start(watchdog_ms)

    def _ok(path_like):
        watchdog.stop(); _cleanup()
        try:
            apply_inplace_update(parent, Path(str(path_like)))
        except Exception as ex:
            QMessageBox.warning(parent, "Update", f"Failed to apply update:\n{ex}")

    def _uptodate():
        watchdog.stop(); _cleanup()
        QMessageBox.information(parent, "Updates", f"You're on the latest version (v{current_version}).")

    def _err(msg):
        watchdog.stop(); _cleanup()
        r = QMessageBox.question(
            parent, "Update failed",
            f"{msg}\n\nOpen Releases page to download manually?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if r == QMessageBox.Yes:
            _open_releases_page(repo)

    w.done.connect(_ok)
    w.up_to_date.connect(_uptodate)
    w.error.connect(_err)
    w.start()
