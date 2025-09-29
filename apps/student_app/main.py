# apps/student_app/main.py
from __future__ import annotations

import json
import json as _json
import shutil
import subprocess
import sys
import urllib.error

# --- quick version helpers ---
import urllib.request
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from time import time
from typing import Optional

from PySide6.QtCore import QSettings, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QIcon, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSplitter,
    QStyle,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from apps.student_app.review_viewer import ReviewData, ReviewItem, open_review_dialog

# Repo core
from paperrepo.repo import commit as repo_commit
from paperrepo.repo import head_commit_id, init_repo, is_repo
from paperrepo.repo import history as repo_history
from paperrepo.repo import restore as repo_restore

# App/shared helpers
from shared.config import (
    get_defaults,
    get_mapping,
    remember_defaults,
    remember_mapping,
)
from shared.detect import detect_manuscript_type  # ✅ đúng module
from shared.events import (
    get_submission_times,
    new_submission_event,
    utcnow_iso,
    write_event,
)
from shared.models import Manifest, ManuscriptType
from shared.osutil import open_with_default_app  # ✅ dùng shared.osutil
from shared.paths import manuscript_root, manuscript_subdirs, slugify
from shared.timeutil import iso_to_local_str

# Updater portable – tương thích API cũ/lẫn mới
from shared.updater import cleanup_legacy_appdata_if_any, download_and_stage_update
from shared.version import APP_VERSION, GITHUB_REPO


def _vtuple(s: str) -> tuple[int, ...]:
    return tuple(int(x) for x in s.split('.') if x.isdigit())

def _is_newer(cur: str, latest: str) -> bool:
    try:
        return _vtuple(cur) < _vtuple(latest)
    except Exception:
        # nếu parse lỗi, coi như có update để không chặn người dùng
        return True

def _fetch_latest_version(repo: str, timeout_sec: float = 6.0) -> str | None:
    """
    Trả về 'x.y.z' từ /releases/latest, hoặc None nếu lỗi/không có.
    """
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(url, headers={"User-Agent": "Paperforge-Updater"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            data = _json.loads(resp.read().decode("utf-8"))
        tag = (data.get("tag_name") or "").strip()
        if not tag:
            return None
        return tag.lstrip('v').strip()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return None


APP_NAME = "Paperforge — Student"


# ─────────────────────────────────────────────────────────────────────────────
# Small utilities
# ─────────────────────────────────────────────────────────────────────────────
def write_minimal_paper_yaml(dst: Path, title: str, journal: str = "") -> None:
    """Write a minimal paper.yaml so the supervisor can see metadata early."""
    data = {"title": title, "journal": journal, "authors": [], "status": "draft"}
    (dst / "paper.yaml").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


class UpdateWorker(QThread):
    done = Signal(object)       # path exe/installer mới (Path hoặc str)
    up_to_date = Signal()
    error = Signal(str)

    def run(self):
        from shared.updater import download_and_stage_update
        from shared.version import APP_VERSION, GITHUB_REPO
        try:
            try:
                # API cũ: (repo, keyword, version, app_id) -> path or None
                res = download_and_stage_update(GITHUB_REPO, "Student", APP_VERSION, app_id="student")
            except TypeError:
                # API mới: (app_id) -> (status, detail)
                res = download_and_stage_update("student")

            if isinstance(res, tuple):
                status, detail = res
                if status == "up_to_date":
                    self.up_to_date.emit(); return
                if status == "staged":
                    # detail: path tải xong
                    self.done.emit(detail); return
                self.error.emit(str(detail)); return

            # API cũ
            if isinstance(res, (str, Path)) and res:
                self.done.emit(res); return

            self.up_to_date.emit()

        except Exception as e:
            msg = str(e)
            if "404" in msg or "Not Found" in msg:
                self.up_to_date.emit()
            else:
                self.error.emit(msg)


# ─────────────────────────────────────────────────────────────────────────────
# Main window
# ─────────────────────────────────────────────────────────────────────────────
class StudentWindow(QMainWindow):
    """
    Modernised Student app:
      • Top toolbar with icons & shortcuts.
      • Header “card” shows working folder, always copyable.
      • Resizable panes: History (top), Inbox + Comments preview (bottom).
      • Inbox quick search filter.
      • Manual "Check for updates…" (không auto-check).
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1200, 820)

        # ── Toolbar ────────────────────────────────────────────────────────
        tb = QToolBar("Quick actions", self)
        tb.setIconSize(QSize(18, 18))
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(tb)

        style = self.style()

        def std_icon(sp):
            return style.standardIcon(sp)

        act_new = QAction(std_icon(QStyle.SP_FileIcon), "New", self)
        act_open = QAction(std_icon(QStyle.SP_DirOpenIcon), "Open", self)
        act_commit = QAction(std_icon(QStyle.SP_DialogSaveButton), "Commit", self)
        act_submit = QAction(std_icon(QStyle.SP_ArrowRight), "Submit", self)
        act_setroot = QAction(
            std_icon(QStyle.SP_DirLinkIcon), "Set/Change Students’ Root…", self
        )
        act_hist = QAction(std_icon(QStyle.SP_BrowserReload), "Refresh history", self)
        act_inbox = QAction(std_icon(QStyle.SP_BrowserReload), "Refresh inbox", self)
        act_restore = QAction(std_icon(QStyle.SP_DialogResetButton), "Restore…", self)
        act_update = QAction(std_icon(QStyle.SP_BrowserReload), "Check for updates…", self)

        # Shortcuts (Mac-friendly)
        act_new.setShortcut(QKeySequence.New)
        act_open.setShortcut(QKeySequence.Open)
        act_commit.setShortcut(QKeySequence("Ctrl+S"))
        act_submit.setShortcut(QKeySequence("Ctrl+Return"))
        act_setroot.setShortcut(QKeySequence("Ctrl+Shift+L"))
        act_hist.setShortcut(QKeySequence("Shift+F5"))
        act_inbox.setShortcut(QKeySequence("F5"))
        act_restore.setShortcut(QKeySequence("Ctrl+R"))

        act_new.triggered.connect(self.create_new)
        act_open.triggered.connect(self.open_existing)
        act_commit.triggered.connect(self.commit_snapshot)
        act_submit.triggered.connect(self.submit_to_supervisor)
        act_setroot.triggered.connect(self.change_remote_for_current)
        act_hist.triggered.connect(self._refresh_history)
        act_inbox.triggered.connect(self.refresh_inbox)
        act_restore.triggered.connect(self.restore_selected_commit)
        act_update.triggered.connect(self._check_updates)

        for a in (
            act_new,
            act_open,
            act_commit,
            act_submit,
            act_setroot,
            act_hist,
            act_inbox,
            act_restore,
        ):
            tb.addAction(a)
        tb.addSeparator()
        tb.addAction(act_update)

        # ── Central layout ────────────────────────────────────────────────
        central = QWidget(self)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(12, 8, 12, 12)
        outer.setSpacing(10)

        # Header “card”
        self.header_title = QLabel("Manuscript: (none)", self)
        self.header_title.setStyleSheet("font-size: 16px; font-weight: 600;")
        self.working_label = QLineEdit(self)
        self.working_label.setReadOnly(True)
        self.working_label.setPlaceholderText("Working folder: (none)")
        self.working_label.setStyleSheet("QLineEdit { background: #f7f7f7; }")
        self.mapping_label = QLabel("Remote mapping: (none)", self)
        self.mapping_label.setStyleSheet("color:#555;")
        header = QVBoxLayout()
        header.addWidget(self.header_title)
        header.addWidget(self.working_label)
        header.addWidget(self.mapping_label)
        header_box = QGroupBox("")
        header_box.setLayout(header)
        header_box.setStyleSheet(
            "QGroupBox { border: 1px solid #e3e3e3; border-radius: 8px; margin-top: 4px; }"
        )
        outer.addWidget(header_box)

        # Splitter: top (History) / bottom (Inbox + Comments)
        split_main = QSplitter(Qt.Vertical, self)

        # History group
        hist_box = QGroupBox("History (newest first)")
        hist_layout = QHBoxLayout(hist_box)
        self.history_list = QListWidget(self)
        self.history_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.history_list.itemSelectionChanged.connect(self._on_history_selection)

        # Right-side history actions
        hist_btns = QVBoxLayout()
        self.btn_refresh_hist = QPushButton("Refresh")
        self.btn_restore = QPushButton("Restore to working copy…")
        self.btn_refresh_hist.clicked.connect(self._refresh_history)
        self.btn_restore.clicked.connect(self.restore_selected_commit)
        self.btn_restore.setEnabled(False)
        hist_btns.addWidget(self.btn_refresh_hist)
        hist_btns.addWidget(self.btn_restore)
        hist_btns.addStretch(1)

        hist_layout.addWidget(self.history_list, stretch=1)
        hist_layout.addLayout(hist_btns)

        # Inbox + comments splitter
        split_bottom = QSplitter(Qt.Horizontal, self)

        # Inbox
        inbox_box = QGroupBox("Inbox — reviews returned by supervisor")
        inbox_layout = QVBoxLayout(inbox_box)
        # Search field
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Filter:"))
        self.inbox_filter = QLineEdit(self)
        self.inbox_filter.setPlaceholderText(
            "Search in submission id / filename / label"
        )
        self.inbox_filter.textChanged.connect(self._apply_inbox_filter)
        search_row.addWidget(self.inbox_filter)
        inbox_layout.addLayout(search_row)

        self.inbox_list = QListWidget(self)
        self.inbox_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.inbox_list.itemSelectionChanged.connect(self._on_inbox_selection)
        inbox_layout.addWidget(self.inbox_list, stretch=1)

        inbox_btns = QHBoxLayout()
        self.btn_refresh_inbox = QPushButton("Refresh inbox")
        self.btn_open_review = QPushButton("Open selected review")
        self.btn_pull_review = QPushButton("Save a copy to working folder")
        self.btn_refresh_inbox.clicked.connect(self.refresh_inbox)
        self.btn_open_review.clicked.connect(self.open_selected_review)
        self.btn_pull_review.clicked.connect(self.pull_selected_review)
        self.btn_open_review.setEnabled(False)
        self.btn_pull_review.setEnabled(False)
        inbox_btns.addWidget(self.btn_refresh_inbox)
        inbox_btns.addStretch(1)
        inbox_btns.addWidget(self.btn_open_review)
        inbox_btns.addWidget(self.btn_pull_review)
        inbox_layout.addLayout(inbox_btns)

        # Comments
        comments_box = QGroupBox("Comments (read-only preview)")
        comments_layout = QVBoxLayout(comments_box)
        self.comments_preview = QTextEdit(self)
        self.comments_preview.setReadOnly(True)
        self.comments_preview.setPlaceholderText("No comments selected.")
        comments_layout.addWidget(self.comments_preview)

        # Assemble splitters
        split_bottom.addWidget(inbox_box)
        split_bottom.addWidget(comments_box)
        split_bottom.setSizes([600, 600])

        split_main.addWidget(hist_box)
        split_main.addWidget(split_bottom)
        split_main.setSizes([350, 470])

        outer.addWidget(split_main, stretch=1)
        self.setCentralWidget(central)

        # Footer credit + version label
        credit = QLabel("Made by Minh Quach", self)
        credit.setStyleSheet("color:#666; margin-top:6px;")
        self.statusBar().addPermanentWidget(credit)
        self.lbl_ver = QLabel(f"v{APP_VERSION}", self)
        self.lbl_ver.setStyleSheet("color:#666; margin-left:12px;")
        self.statusBar().addPermanentWidget(self.lbl_ver)

        # State
        self.working_dir: Optional[Path] = None

        # Initial disables
        self.btn_refresh_inbox.setEnabled(False)

        # Stylesheet
        self.setStyleSheet(
            """
            QListWidget { font-size: 13px; }
            QPushButton { padding: 6px 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
        """
        )

        # Save/restore window state
        self._settings = QSettings("Paperforge", "Student")
        if self._settings.value("geometry"):
            self.restoreGeometry(self._settings.value("geometry"))
        if self._settings.value("state"):
            self.restoreState(self._settings.value("state"))

        self.statusBar().showMessage("Ready", 3000)

        # Dọn cơ chế AppData cũ (nếu từng dùng)
        cleanup_legacy_appdata_if_any()
        # KHÔNG auto-check update để tránh loop/not responding

    # ──────────────────────────────────────────────────────────────────────
    # Updates (manual, in-place swap trên Windows)
    # ──────────────────────────────────────────────────────────────────────
    def _apply_inplace_update(self, staged_path: Path) -> None:
        """
        Windows portable: copy exe mới về đúng thư mục hiện tại, swap an toàn bằng .cmd,
        rồi tự khởi động lại chính đường dẫn cũ.
        macOS/Linux: mở thư mục chứa file tải về để người dùng thay thủ công.
        """
        try:
            if sys.platform.startswith("win"):
                exe = Path(sys.executable).resolve()
                exe_dir = exe.parent
                staged_path = Path(staged_path).resolve()
                if not staged_path.exists():
                    QMessageBox.warning(
                        self, "Update", f"Downloaded file missing:\n{staged_path}"
                    )
                    return

                # Copy về cạnh file đang chạy
                new_copy = exe_dir / (exe.name + ".new")
                shutil.copy2(staged_path, new_copy)

                # Tạo script swap
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

                # Nếu staged ở AppData thì dọn nhẹ
                try:
                    if "AppData" in str(staged_path):
                        shutil.rmtree(staged_path.parent, ignore_errors=True)
                except Exception:
                    pass

                subprocess.Popen(["cmd", "/c", str(swap)], close_fds=True)
                QApplication.quit()
            else:
                QMessageBox.information(
                    self,
                    "Update downloaded",
                    "An update has been downloaded. Please replace your app with the new one.",
                )
                p = Path(staged_path)
                if p.exists():
                    if sys.platform == "darwin":
                        subprocess.run(["open", str(p.parent)], check=False)
                    else:
                        subprocess.run(["xdg-open", str(p.parent)], check=False)
        except Exception as e:
            QMessageBox.warning(self, "Update", f"Failed to apply update:\n{e}")

    def _check_updates(self) -> None:
        from shared.version import APP_VERSION, GITHUB_REPO
        ans = QMessageBox.question(
            self, "Check for updates",
            f"Current version: v{APP_VERSION}\nCheck online for a new version now?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if ans != QMessageBox.Yes:
            return

        latest = _fetch_latest_version(GITHUB_REPO, timeout_sec=6)
        if not latest:
            QMessageBox.information(self, "Updates", "Couldn't reach update server. Please try again later.")
            return

        if not _is_newer(APP_VERSION, latest):
            QMessageBox.information(self, "Updates", f"You're on the latest version (v{APP_VERSION}).")
            return

        # Có bản mới -> chạy worker với progress + watchdog timeout
        dlg = QProgressDialog("Downloading update…", None, 0, 0, self)
        dlg.setWindowModality(Qt.ApplicationModal)
        dlg.setCancelButton(None)
        dlg.setWindowTitle("Updates")
        dlg.show()
        self._update_dlg = dlg

        w = UpdateWorker(self)
        self._update_worker = w

        def _cleanup():
            if getattr(self, "_update_dlg", None):
                self._update_dlg.close()
                self._update_dlg = None
            self._update_worker = None

        # watchdog: 30s mà chưa xong thì cắt
        self._update_watchdog = QTimer(self)
        self._update_watchdog.setSingleShot(True)
        def _on_timeout():
            try:
                if self._update_worker and self._update_worker.isRunning():
                    self._update_worker.terminate()  # hard stop (chấp nhận cho TH mạng kẹt)
            finally:
                _cleanup()
                QMessageBox.warning(self, "Updates", "Timed out while downloading. Please try again later.")
        self._update_watchdog.timeout.connect(_on_timeout)
        self._update_watchdog.start(30_000)

        def _finish_ok(path_like):
            self._update_watchdog.stop()
            _cleanup()
            # với updater cũ: mở exe mới hoặc áp dụng in-place (tuỳ bạn đã cài)
            try:
                self._apply_inplace_update(Path(str(path_like)))
            except Exception as ex:
                QMessageBox.warning(self, "Update", f"Failed to apply update:\n{ex}")

        def _finish_uptodate():
            self._update_watchdog.stop()
            _cleanup()
            QMessageBox.information(self, "Updates", f"You're on the latest version (v{APP_VERSION}).")

        def _finish_err(msg):
            self._update_watchdog.stop()
            _cleanup()
            QMessageBox.warning(self, "Update failed", msg)

        w.done.connect(_finish_ok)
        w.up_to_date.connect(_finish_uptodate)
        w.error.connect(_finish_err)
        w.start()


    # ──────────────────────────────────────────────────────────────────────
    # Small helpers
    # ──────────────────────────────────────────────────────────────────────
    def _set_working_dir(self, path: Path) -> None:
        self.working_dir = path
        self.header_title.setText(f"Manuscript: {path.name}")
        self.working_label.setText(str(path))
        self._update_mapping_label()
        self.btn_refresh_inbox.setEnabled(True)
        self._refresh_history()
        self.refresh_inbox()

    def _update_mapping_label(self) -> None:
        if not self.working_dir:
            self.mapping_label.setText("Remote mapping: (none)")
            return
        m = get_mapping(self.working_dir)
        if m:
            root = m.get("students_root", "")
            who = m.get("student_name", "")
            slug = m.get("slug", "")
            self.mapping_label.setText(f"Remote: {root} → {who}/{slug}")
        else:
            self.mapping_label.setText("Remote mapping: (none)")

    def _fmt_time(self, ts: float) -> str:
        dt = datetime.fromtimestamp(ts)
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    def _on_history_selection(self) -> None:
        self.btn_restore.setEnabled(bool(self.history_list.selectedItems()))

    def _on_inbox_selection(self) -> None:
        has = bool(self.inbox_list.selectedItems())
        self.btn_open_review.setEnabled(has)
        self.btn_pull_review.setEnabled(has)
        self._load_comments_preview()

    # ──────────────────────────────────────────────────────────────────────
    # Create / Open
    # ──────────────────────────────────────────────────────────────────────
    def create_new(self) -> None:
        # Chọn parent
        parent = QFileDialog.getExistingDirectory(self, 'Choose a parent directory for the manuscript')
        if not parent:
            return

        # Nhập tên + journal
        name, ok = QInputDialog.getText(self, 'Manuscript name', 'Enter a manuscript name (e.g. Paper 1):')
        if not ok or not name.strip():
            return
        journal, ok = QInputDialog.getText(self, 'Target journal (optional)', 'Enter target journal (optional):')
        if not ok:
            return

        slug = slugify(name)
        new_dir = Path(parent) / slug

        if new_dir.exists():
            # Nếu đã tồn tại: hỏi có dùng luôn không (chỉ tiếp tục nếu trống)
            if any(new_dir.iterdir()):
                QMessageBox.warning(self, 'Folder exists',
                                    f'The folder already exists and is not empty:\n{new_dir}\n\n'
                                    'Please choose another name or remove the folder.')
                return
        else:
            new_dir.mkdir(parents=True, exist_ok=True)

        # Ghi metadata sớm
        try:
            write_minimal_paper_yaml(new_dir, title=name.strip(), journal=journal.strip())
        except Exception as e:
            QMessageBox.critical(self, 'Error writing paper.yaml', str(e))
            return

        # KHỞI TẠO REPO – KHÔNG NUỐT LỖI
        try:
            init_repo(new_dir)
        except Exception as e:
            QMessageBox.critical(self, 'Init repository failed',
                                f'Could not create repository at:\n{new_dir}\n\n{e}')
            return

        if not is_repo(new_dir):
            QMessageBox.critical(self, 'Repository not found',
                                f'Init succeeded but repo not detected at:\n{new_dir}')
            return

        # Commit đầu tiên
        try:
            c = repo_commit(new_dir, message=f'Initial snapshot: {name.strip()}')
            self.statusBar().showMessage(f'Initialised repo and committed {c.id[:7]}', 4000)
        except Exception as e:
            # Repo đã có cũng OK, nhưng cảnh báo việc chưa có checkpoint
            QMessageBox.warning(self, 'Initial commit failed',
                                f'Repository initialised but initial commit failed.\n\n{e}')

        # Cập nhật UI + bật luôn thư mục làm việc
        self._set_working_dir(new_dir)
        QMessageBox.information(self, 'New manuscript',
                                f'Created manuscript folder and repository:\n{new_dir}')


    def open_existing(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select manuscript folder")
        if not folder:
            return
        path = Path(folder)

        # 1) Trường hợp chọn đúng thư mục manuscript
        if is_repo(path):
            self.statusBar().showMessage("Manuscript ready.", 3000)
            self._set_working_dir(path)
            return

        # 2) Không có repo tại đây → thử tìm repo con (để bắt case chọn nhầm StudentA/)
        #    Ưu tiên quét 1 cấp (StudentA/*), sau đó mở rộng nhẹ tới cấp 2 (StudentA/*/*)
        child_repos = [d for d in path.iterdir() if d.is_dir() and is_repo(d)]
        if not child_repos:
            level2 = []
            for d1 in path.iterdir():
                if not d1.is_dir():
                    continue
                try:
                    for d2 in d1.iterdir():
                        if d2.is_dir() and is_repo(d2):
                            level2.append(d2)
                except Exception:
                    pass
            child_repos = level2

        if child_repos:
            # Tìm thấy repo con → cho chọn (nếu chỉ 1 thì mở luôn)
            if len(child_repos) == 1:
                chosen = child_repos[0]
            else:
                names = [str(p) for p in child_repos]
                chosen_str, ok = QInputDialog.getItem(
                    self,
                    "Choose manuscript",
                    "This folder has no repository.\nSelect a manuscript inside:",
                    names,
                    0,
                    False,
                )
                if not ok or not chosen_str:
                    return
                chosen = Path(chosen_str)

            self.statusBar().showMessage(f"Opening nested manuscript: {chosen}", 4000)
            self._set_working_dir(chosen)
            return

        # 3) Không thấy repo con → hỏi có init repo ở đây không (giữ hành vi cũ)
        resp = QMessageBox.question(
            self,
            "Initialise repository?",
            "This folder has no repository (.paperrepo). Do you want to initialise it now?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if resp == QMessageBox.Yes:
            try:
                init_repo(path)
                repo_commit(path, message="Initial snapshot (auto)")
            except Exception as e:
                QMessageBox.critical(self, "Init repository failed", str(e))
                return
            self.statusBar().showMessage("Repository initialised.", 3000)
            self._set_working_dir(path)


    # ──────────────────────────────────────────────────────────────────────
    # Commit / History / Restore
    # ──────────────────────────────────────────────────────────────────────
    def commit_snapshot(self) -> None:
        if not self.working_dir:
            QMessageBox.warning(
                self, "No manuscript", "Please select or create a manuscript folder first."
            )
            return
        if not is_repo(self.working_dir):
            init_repo(self.working_dir)

        message, ok = QInputDialog.getText(
            self, "Commit message", "Describe your changes:", text="Checkpoint"
        )
        if not ok or not message.strip():
            return

        c = repo_commit(self.working_dir, message=message.strip())
        self.statusBar().showMessage(
            f"Committed {c.id[:7]} at {int(c.timestamp)}", 5000
        )
        self._refresh_history()

    def _refresh_history(self) -> None:
        self.history_list.clear()
        if not self.working_dir or not is_repo(self.working_dir):
            return
        commits = repo_history(self.working_dir)
        for i, c in enumerate(commits):
            title = c.message.splitlines()[0] if c.message else "(no message)"
            when = self._fmt_time(c.timestamp)
            text = f"{i + 1:02d} | {when} | {title} | {c.id[:12]}"
            item = QListWidgetItem(text, self.history_list)
            item.setData(Qt.UserRole, c.id)

    def restore_selected_commit(self) -> None:
        if not self.working_dir:
            return
        items = self.history_list.selectedItems()
        if not items:
            return
        commit_id = items[0].data(Qt.UserRole)

        box = QMessageBox(self)
        box.setWindowTitle("Restore working copy")
        box.setText(
            "Do you want to CLEAN the working folder before restoring?\n\n"
            "Yes = Clean (remove existing files except .paperrepo etc.)\n"
            "No = Overlay (keep unrelated files, overwrite tracked ones)\n"
            "Cancel = abort."
        )
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
        box.setDefaultButton(QMessageBox.No)
        resp = box.exec()

        if resp == QMessageBox.Cancel:
            return
        clean = resp == QMessageBox.Yes

        try:
            written = repo_restore(self.working_dir, commit_id=commit_id, clean=clean)
        except Exception as e:
            QMessageBox.critical(self, "Restore failed", str(e))
            return

        self.statusBar().showMessage(
            f"Restored {written} file(s) from {commit_id[:12]}", 6000
        )
        QMessageBox.information(
            self, "Restored", f"Working copy restored to commit:\n{commit_id[:12]}"
        )

    # ──────────────────────────────────────────────────────────────────────
    # Mapping / Inbox
    # ──────────────────────────────────────────────────────────────────────
    def change_remote_for_current(self) -> None:
        if not self.working_dir:
            QMessageBox.warning(self, "No manuscript", "Open a manuscript first.")
            return
        current = get_mapping(self.working_dir) or {}
        newmap = self._prompt_for_mapping(current)
        if newmap:
            self._update_mapping_label()
            self.btn_refresh_inbox.setEnabled(True)
            self.refresh_inbox()
            QMessageBox.information(
                self,
                "Mapping updated",
                f'Now linked to:\n{newmap["students_root"]}\n{newmap["student_name"]}/{newmap["slug"]}',
            )

    def _ensure_mapping(self) -> Optional[dict]:
        if not self.working_dir:
            return None

        mapping = get_mapping(self.working_dir)
        if mapping:
            return mapping

        defaults = get_defaults()
        students_root_dir = QFileDialog.getExistingDirectory(
            self,
            "Select Students’ Root (OneDrive)",
            dir=defaults.get("students_root") or "",
        )
        if not students_root_dir:
            return None

        student_name, ok = QInputDialog.getText(
            self,
            "Student name",
            "Enter your display name (as used by the supervisor):",
            text=defaults.get("student_name") or "",
        )
        if not ok or not student_name.strip():
            return None

        default_slug = slugify(self.working_dir.name)
        manuscript_slug, ok = QInputDialog.getText(
            self,
            "Manuscript slug",
            "Slug for this manuscript folder:",
            text=default_slug,
        )
        if not ok or not manuscript_slug.strip():
            return None
        manuscript_slug = slugify(manuscript_slug)

        remember_defaults(students_root_dir, student_name.strip())
        remember_mapping(
            self.working_dir, students_root_dir, student_name.strip(), manuscript_slug
        )

        return get_mapping(self.working_dir)

    def _prompt_for_mapping(self, preset: Optional[dict] = None) -> Optional[dict]:
        if not self.working_dir:
            QMessageBox.warning(self, "No manuscript", "Open a manuscript first.")
            return None

        defaults = get_defaults()
        start_dir = (
            (preset or {}).get("students_root")
            or defaults.get("students_root")
            or ""
        )
        students_root_dir = QFileDialog.getExistingDirectory(
            self, "Select Students’ Root (OneDrive)", dir=start_dir
        )
        if not students_root_dir:
            return None

        student_name_default = (
            (preset or {}).get("student_name") or defaults.get("student_name") or ""
        )
        student_name, ok = QInputDialog.getText(
            self,
            "Student name",
            "Enter your display name (as used by the supervisor):",
            text=student_name_default,
        )
        if not ok or not student_name.strip():
            return None

        slug_default = (preset or {}).get("slug") or slugify(self.working_dir.name)
        manuscript_slug, ok = QInputDialog.getText(
            self,
            "Manuscript slug",
            "Slug for this manuscript folder:",
            text=slug_default,
        )
        if not ok or not manuscript_slug.strip():
            return None
        manuscript_slug = slugify(manuscript_slug)

        # Save
        remember_defaults(students_root_dir, student_name.strip())
        remember_mapping(
            self.working_dir, students_root_dir, student_name.strip(), manuscript_slug
        )

        return {
            "students_root": students_root_dir,
            "student_name": student_name.strip(),
            "slug": manuscript_slug,
        }

    def _apply_inbox_filter(self) -> None:
        q = (self.inbox_filter.text() or "").strip().lower()
        for i in range(self.inbox_list.count()):
            it = self.inbox_list.item(i)
            it.setHidden(q not in it.text().lower())

    def refresh_inbox(self) -> None:
        self.inbox_list.clear()
        if self.comments_preview:
            self.comments_preview.clear()
            self.comments_preview.setPlaceholderText("No comments selected.")
        if not self.working_dir:
            return

        mapping = get_mapping(self.working_dir)
        if not mapping:
            self.btn_open_review.setEnabled(False)
            return

        students_root = Path(mapping["students_root"])
        student_name = mapping["student_name"]
        slug = mapping["slug"]

        mroot = students_root / student_name / slug
        reviews = mroot / "reviews"
        if not reviews.exists():
            self.btn_open_review.setEnabled(False)
            return

        events_dir = mroot / "events"
        count = 0

        for subdir in sorted(reviews.iterdir(), key=lambda p: p.name, reverse=True):
            if not subdir.is_dir():
                continue
            sub_id = subdir.name
            docx = subdir / "returned.docx"
            doc = subdir / "returned.doc"
            html = subdir / "review.html"  # pre-return preview (latex)
            rhtml = subdir / "returned.html"  # post-return (latex)

            target, label = None, None
            if docx.exists():
                target, label = docx, "returned.docx"
            elif doc.exists():
                target, label = doc, "returned.doc"
            elif rhtml.exists():
                target, label = rhtml, "returned.html"
            elif html.exists():
                target, label = html, "review.html"
            else:
                continue

            sub_ts, ret_ts = get_submission_times(events_dir, sub_id)
            when = f"submitted {iso_to_local_str(sub_ts)}"
            if ret_ts:
                when = f"returned {iso_to_local_str(ret_ts)}"

            item = QListWidgetItem(
                f"Submission {sub_id} — {label} · {when}", self.inbox_list
            )
            item.setData(Qt.UserRole, str(target))
            item.setData(Qt.UserRole + 1, sub_id)
            item.setData(Qt.UserRole + 2, str((target.parent / "comments.json")))
            count += 1

        self.btn_open_review.setEnabled(count > 0)
        self._apply_inbox_filter()

    def open_selected_review(self) -> None:
        items = self.inbox_list.selectedItems()
        if not items:
            return

        sel_path = Path(items[0].data(Qt.UserRole))
        sub_id = items[0].data(Qt.UserRole + 1) or "unknown"
        cjson = Path(items[0].data(Qt.UserRole + 2) or "")

        if not sel_path.exists():
            QMessageBox.warning(self, "Missing file", f"Review file not found:\n{sel_path}")
            return

        folder = sel_path.parent

        # --- pick primary PDF (prefer *_diff.pdf) ---
        def _first(glob_pat: str) -> Optional[str]:
            for p in sorted(folder.glob(glob_pat)):
                return str(p)
            return None

        pdf_path = None
        diff_pdf = _first("*diff*.pdf")
        if sel_path.suffix.lower() == ".pdf":
            pdf_path = str(sel_path)
        elif diff_pdf:
            pdf_path = diff_pdf
        else:
            pdf_path = _first("*.pdf")

        # --- load comments.json -> general / comments / itemised ---
        general_notes = ""
        comments_list = []
        item_objs: list[ReviewItem] = []

        if cjson.exists():
            try:
                d = json.loads(cjson.read_text(encoding="utf-8"))
                general_notes = d.get("general") or ""
                comments_list = d.get("comments") or []
                for it in (d.get("items") or []):
                    f = it.get("file", "")
                    ls = it.get("line_start", it.get("line", ""))
                    le = it.get("line_end", ls)
                    msg = it.get("text", "")
                    linestr = str(ls) if ls == le else f"{ls}-{le}"
                    item_objs.append(ReviewItem(file=f, lines=linestr, message=msg))
            except Exception as e:
                general_notes = f"(Failed to parse comments.json: {e})"

        # --- build log (best-effort) ---
        build_log = ""
        for cand in ("build.log", "latexmk.log", "pdflatex.log", "log.txt"):
            p = folder / cand
            if p.exists():
                try:
                    build_log = p.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    pass
                break

        # --- sources: list .tex (limited) ---
        sources: list[tuple[str, str]] = []
        texs = list(folder.glob("*.tex")) or list(folder.glob("**/*.tex"))
        for p in texs[:30]:
            sources.append((p.name, str(p)))

        # --- build ReviewData and open dialog ---
        review = ReviewData(
            title=f"Review — submission {sub_id}",
            status="Returned" if "returned" in sel_path.name.lower() else "Preview",
            pdf_path=pdf_path,
            diff_pdf_path=diff_pdf,
            general_notes=general_notes,
            comments=comments_list,
            items=item_objs,
            build_log=build_log,
            sources=sources,
        )

        # If no PDF but HTML exists, open HTML externally (viewer sẽ vẫn mở để xem comments)
        if not review.pdf_path:
            for cand in ("returned.html", "review.html"):
                hp = folder / cand
                if hp.exists():
                    try:
                        open_with_default_app(hp)
                    except Exception:
                        pass
                    break

        open_review_dialog(self, review)


    def pull_selected_review(self) -> None:
        if not self.working_dir:
            QMessageBox.warning(
                self, "No manuscript", "Please select or create a manuscript folder first."
            )
            return
        items = self.inbox_list.selectedItems()
        if not items:
            return

        src = Path(items[0].data(Qt.UserRole))
        sub_id = items[0].data(Qt.UserRole + 1) or "unknown"
        if not src.exists():
            QMessageBox.warning(self, "Missing file", f"Review file not found:\n{src}")
            return

        dest_dir = self.working_dir / "received_reviews" / sub_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"returned{src.suffix.lower()}"

        try:
            shutil.copy2(src, dest)
            comments = src.parent / "comments.json"
            if comments.exists():
                shutil.copy2(comments, dest_dir / "comments.json")
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))
            return

        resp = QMessageBox.question(
            self,
            "Create checkpoint?",
            "A copy of the review has been saved locally.\n\n"
            "Do you want to create a checkpoint to record this in history?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if resp == QMessageBox.Yes:
            try:
                repo_commit(
                    self.working_dir,
                    message=f"Save supervisor review for submission {sub_id}",
                )
                self._refresh_history()
            except Exception:
                pass

        self.statusBar().showMessage(f"Saved review to: {dest}", 6000)
        QMessageBox.information(self, "Saved", f"Review saved to:\n{dest}")

    def _load_comments_preview(self) -> None:
        if not self.comments_preview:
            return
        self.comments_preview.clear()
        items = self.inbox_list.selectedItems()
        if not items:
            self.comments_preview.setPlaceholderText("No comments selected.")
            return
        cpath = Path(items[0].data(Qt.UserRole + 2) or "")
        if not cpath.exists():
            self.comments_preview.setPlaceholderText(
                "No comments.json found for this review."
            )
            return

        try:
            data = json.loads(cpath.read_text(encoding="utf-8"))
        except Exception as e:
            self.comments_preview.setPlainText(f"Failed to read comments.json:\n{e}")
            return

        general = (data.get("general") or "").strip()
        items_list = data.get("items") or []

        lines = []
        if general:
            lines += ["GENERAL NOTES", "-------------", general, ""]
        if items_list:
            lines += ["ITEMISED COMMENTS", "-----------------"]
            for i, it in enumerate(items_list, 1):
                f = it.get("file", "")
                ls = it.get("line_start", it.get("line", ""))
                le = it.get("line_end", ls)
                t = it.get("text", "")
                loc = f"{f}:{ls}" if ls == le else f"{f}:{ls}-{le}"
                lines.append(f"{i:02d}. {loc} — {t}")

        if not lines:
            self.comments_preview.setPlaceholderText("No comments in this review.")
        else:
            self.comments_preview.setPlainText("\n".join(lines))

    # ──────────────────────────────────────────────────────────────────────
    # Submit
    # ──────────────────────────────────────────────────────────────────────
    def submit_to_supervisor(self) -> None:
        if not is_repo(self.working_dir):
            try:
                init_repo(self.working_dir)
            except Exception:
                pass

        if not head_commit_id(self.working_dir):
            # đảm bảo luôn có checkpoint trước khi “đóng gói”
            try:
                repo_commit(self.working_dir, message='Initial snapshot (auto)')
            except Exception:
                pass

        if not self.working_dir:
            QMessageBox.warning(
                self, "No manuscript", "Please select or create a manuscript folder first."
            )
            return

        if not head_commit_id(self.working_dir):
            repo_commit(self.working_dir, message="Initial snapshot (auto)")

        message, ok = QInputDialog.getText(
            self,
            "Commit message",
            "Message for this submission:",
            text="Work ready for review",
        )
        if ok and message.strip():
            repo_commit(self.working_dir, message=message.strip())

        # Select mapping or create
        mapping = self._ensure_mapping()
        if not mapping:
            return

        students_root_dir = mapping["students_root"]
        student_name = mapping["student_name"]
        manuscript_slug = mapping["slug"]

        dest_root = manuscript_root(Path(students_root_dir), student_name, manuscript_slug)
        subs = manuscript_subdirs(dest_root)

        # Create submission package
        submission_id = datetime.utcnow().strftime("%Y%m%d%H%M%S")  # stable id
        dest = subs["submissions"] / submission_id
        payload = dest / "payload"
        payload.mkdir(parents=True, exist_ok=True)

        for p in self.working_dir.rglob("*"):
            if p.is_dir():
                continue
            rel = p.relative_to(self.working_dir)
            if any(part in {".paperrepo", "submissions", "reviews", "events"} for part in rel.parts):
                continue
            (payload / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, payload / rel)

        mtype = detect_manuscript_type(payload)

        # Read journal from paper.yaml if present
        journal_val = None
        try:
            paper_cfg = json.loads(
                (self.working_dir / "paper.yaml").read_text(encoding="utf-8")
            )
            journal_val = (paper_cfg.get("journal") or "").strip() or None
        except Exception:
            pass

        manifest = Manifest(
            manuscript_title=self.working_dir.name,
            manuscript_type=mtype,
            commit_id=(head_commit_id(self.working_dir) or ""),
            created_at=time(),
            student_name=student_name,
            manuscript_slug=manuscript_slug,
            notes=message if isinstance(message, str) else None,
            submitted_at=utcnow_iso(),
            journal=journal_val,
        )
        (dest / "manifest.json").write_text(
            json.dumps(asdict(manifest), ensure_ascii=False, indent=2), encoding="utf-8"
        )

        write_event(subs["events"], new_submission_event(submission_id))
        self.statusBar().showMessage(f"Submission created: {submission_id}", 6000)
        QMessageBox.information(
            self, "Submitted", f"Submission has been created:\n{submission_id}"
        )

        self.refresh_inbox()

    # Save window state
    def closeEvent(self, ev):
        if hasattr(self, "_settings"):
            self._settings.setValue("geometry", self.saveGeometry())
            self._settings.setValue("state", self.saveState())
        super().closeEvent(ev)


# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    app = QApplication(sys.argv)
    window = StudentWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
