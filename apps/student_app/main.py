from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from time import time
from typing import Optional

from PySide6.QtCore import QSettings, QSize, Qt, QTimer
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
    QPushButton,
    QSplitter,
    QStyle,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

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
from shared.events import (
    get_submission_times,
    new_submission_event,
    utcnow_iso,
    write_event,
)
from shared.models import Manifest, ManuscriptType
from shared.paths import manuscript_root, manuscript_subdirs, slugify
from shared.timeutil import iso_to_local_str

# ⬇️ Updater portable – tương thích API cũ/lẫn mới
from shared.updater import cleanup_legacy_appdata_if_any, download_and_stage_update
from shared.version import APP_VERSION, GITHUB_REPO

APP_NAME = 'Paperforge — Student'


# ─────────────────────────────────────────────────────────────────────────────
# Small utilities
# ─────────────────────────────────────────────────────────────────────────────
def write_minimal_paper_yaml(dst: Path, title: str, journal: str = '') -> None:
    """Write a minimal paper.yaml so the supervisor can see metadata early."""
    data = {'title': title, 'journal': journal, 'authors': [], 'status': 'draft'}
    (dst / 'paper.yaml').write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8'
    )


def open_with_default_app(path: Path) -> None:
    """Open a file with the system default application."""
    if sys.platform.startswith('win'):
        import os
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == 'darwin':
        subprocess.run(['open', str(path)], check=False)
    else:
        subprocess.run(['xdg-open', str(path)], check=False)


def detect_manuscript_type(root: Path) -> ManuscriptType:
    """
    Robustly detect manuscript type by scanning the payload.
    Treat both .docx and .doc as 'DOCX' (Word flow).
    """
    has_docx = any(p.is_file() and p.suffix.lower() == '.docx' for p in root.rglob('*'))
    has_doc = any(p.is_file() and p.suffix.lower() == '.doc' for p in root.rglob('*'))
    has_tex = any(p.is_file() and p.suffix.lower() == '.tex' for p in root.rglob('*'))
    has_word = has_docx or has_doc
    if has_word and not has_tex:
        return ManuscriptType.DOCX
    if has_tex and not has_word:
        return ManuscriptType.LATEX
    if has_word and has_tex:
        return ManuscriptType.DOCX  # prefer Word for MVP
    return ManuscriptType.DOCX


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
      • Auto-update (silent) + manual Check for updates…
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1200, 820)

        # ── Toolbar ────────────────────────────────────────────────────────
        tb = QToolBar('Quick actions', self)
        tb.setIconSize(QSize(18, 18))
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(tb)

        style = self.style()
        def std_icon(sp): return style.standardIcon(sp)

        act_new = QAction(std_icon(QStyle.SP_FileIcon), 'New', self)
        act_open = QAction(std_icon(QStyle.SP_DirOpenIcon), 'Open', self)
        act_commit = QAction(std_icon(QStyle.SP_DialogSaveButton), 'Commit', self)
        act_submit = QAction(std_icon(QStyle.SP_ArrowRight), 'Submit', self)
        act_setroot = QAction(std_icon(QStyle.SP_DirLinkIcon), 'Set/Change Students’ Root…', self)
        act_hist = QAction(std_icon(QStyle.SP_BrowserReload), 'Refresh history', self)
        act_inbox = QAction(std_icon(QStyle.SP_BrowserReload), 'Refresh inbox', self)
        act_restore = QAction(std_icon(QStyle.SP_DialogResetButton), 'Restore…', self)
        act_update = QAction(std_icon(QStyle.SP_BrowserReload), f'Check for updates… (v{APP_VERSION})', self)

        # Shortcuts (Mac-friendly)
        act_new.setShortcut(QKeySequence.New)
        act_open.setShortcut(QKeySequence.Open)
        act_commit.setShortcut(QKeySequence('Ctrl+S'))
        act_submit.setShortcut(QKeySequence('Ctrl+Return'))
        act_setroot.setShortcut(QKeySequence('Ctrl+Shift+L'))
        act_hist.setShortcut(QKeySequence('Shift+F5'))
        act_inbox.setShortcut(QKeySequence('F5'))
        act_restore.setShortcut(QKeySequence('Ctrl+R'))

        act_new.triggered.connect(self.create_new)
        act_open.triggered.connect(self.open_existing)
        act_commit.triggered.connect(self.commit_snapshot)
        act_submit.triggered.connect(self.submit_to_supervisor)
        act_setroot.triggered.connect(self.change_remote_for_current)
        act_hist.triggered.connect(self._refresh_history)
        act_inbox.triggered.connect(self.refresh_inbox)
        act_restore.triggered.connect(self.restore_selected_commit)
        act_update.triggered.connect(self._check_updates)

        for a in (act_new, act_open, act_commit, act_submit, act_setroot, act_hist, act_inbox, act_restore):
            tb.addAction(a)
        tb.addSeparator()
        tb.addAction(act_update)

        # ── Central layout ────────────────────────────────────────────────
        central = QWidget(self)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(12, 8, 12, 12)
        outer.setSpacing(10)

        # Header “card”
        self.header_title = QLabel('Manuscript: (none)', self)
        self.header_title.setStyleSheet('font-size: 16px; font-weight: 600;')
        self.working_label = QLineEdit(self)
        self.working_label.setReadOnly(True)
        self.working_label.setPlaceholderText('Working folder: (none)')
        self.working_label.setStyleSheet('QLineEdit { background: #f7f7f7; }')
        self.mapping_label = QLabel('Remote mapping: (none)', self)
        self.mapping_label.setStyleSheet('color:#555;')
        header = QVBoxLayout()
        header.addWidget(self.header_title)
        header.addWidget(self.working_label)
        header.addWidget(self.mapping_label)
        header_box = QGroupBox('')
        header_box.setLayout(header)
        header_box.setStyleSheet('QGroupBox { border: 1px solid #e3e3e3; border-radius: 8px; margin-top: 4px; }')
        outer.addWidget(header_box)

        # Splitter: top (History) / bottom (Inbox + Comments)
        split_main = QSplitter(Qt.Vertical, self)

        # History group
        hist_box = QGroupBox('History (newest first)')
        hist_layout = QHBoxLayout(hist_box)
        self.history_list = QListWidget(self)
        self.history_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.history_list.itemSelectionChanged.connect(self._on_history_selection)

        # Right-side history actions
        hist_btns = QVBoxLayout()
        self.btn_refresh_hist = QPushButton('Refresh')
        self.btn_restore = QPushButton('Restore to working copy…')
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
        inbox_box = QGroupBox('Inbox — reviews returned by supervisor')
        inbox_layout = QVBoxLayout(inbox_box)
        # Search field
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel('Filter:'))
        self.inbox_filter = QLineEdit(self)
        self.inbox_filter.setPlaceholderText('Search in submission id / filename / label')
        self.inbox_filter.textChanged.connect(self._apply_inbox_filter)
        search_row.addWidget(self.inbox_filter)
        inbox_layout.addLayout(search_row)

        self.inbox_list = QListWidget(self)
        self.inbox_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.inbox_list.itemSelectionChanged.connect(self._on_inbox_selection)
        inbox_layout.addWidget(self.inbox_list, stretch=1)

        inbox_btns = QHBoxLayout()
        self.btn_refresh_inbox = QPushButton('Refresh inbox')
        self.btn_open_review = QPushButton('Open selected review')
        self.btn_pull_review = QPushButton('Save a copy to working folder')
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
        comments_box = QGroupBox('Comments (read-only preview)')
        comments_layout = QVBoxLayout(comments_box)
        self.comments_preview = QTextEdit(self)
        self.comments_preview.setReadOnly(True)
        self.comments_preview.setPlaceholderText('No comments selected.')
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

        # Footer credit
        credit = QLabel('Made by Minh Quach', self)
        credit.setStyleSheet('color:#666; margin-top:6px;')
        self.statusBar().addPermanentWidget(credit)

        # State
        self.working_dir: Optional[Path] = None

        # Initial disables
        self.btn_refresh_inbox.setEnabled(False)

        # Stylesheet
        self.setStyleSheet("""
            QListWidget { font-size: 13px; }
            QPushButton { padding: 6px 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
        """)

        # Save/restore window state
        self._settings = QSettings('Paperforge', 'Student')
        if self._settings.value('geometry'):
            self.restoreGeometry(self._settings.value('geometry'))
        if self._settings.value('state'):
            self.restoreState(self._settings.value('state'))

        self.statusBar().showMessage('Ready', 3000)

        # Dọn cơ chế AppData cũ (nếu từng dùng)
        cleanup_legacy_appdata_if_any()
        # Auto-check update (silent) sau 3s
        QTimer.singleShot(3000, self._check_updates_silent)

    # ──────────────────────────────────────────────────────────────────────
    # Updates (manual & silent)
    # ──────────────────────────────────────────────────────────────────────
    def _check_updates(self) -> None:
        """Manual check – luôn hiện thông báo."""
        self._do_check_update(silent=False)

    def _check_updates_silent(self) -> None:
        """Silent check – chỉ báo khi có bản mới."""
        self._do_check_update(silent=True)

    def _do_check_update(self, silent: bool) -> None:
        """
        Tương thích:
          - Updater mới (trả ('up_to_date'|'staged'|'error', detail))
          - Updater cũ (trả path exe mới dạng str)
        """
        try:
            if not silent:
                self.statusBar().showMessage('Checking updates…', 3000)

            res = None
            try:
                # API cũ: cần GITHUB_REPO + app_keyword + version
                res = download_and_stage_update(GITHUB_REPO, "Student", APP_VERSION, app_id="student")
            except TypeError:
                # API mới: chỉ truyền app_id
                res = download_and_stage_update("student")

            # ── Xử lý kết quả
            if isinstance(res, tuple):
                status, detail = res
                if status == "up_to_date":
                    if not silent:
                        QMessageBox.information(self, "Updates", f"You're on the latest version (v{APP_VERSION}).")
                    else:
                        self.statusBar().showMessage("Up-to-date.", 3000)
                    return
                if status == "staged":
                    QMessageBox.information(self, "Update", "Update has been staged. The app will restart.")
                    QApplication.quit()
                    return
                # error
                if not silent:
                    QMessageBox.warning(self, "Update", f"Update check failed: {detail}")
                else:
                    self.statusBar().showMessage(f"Update check failed: {detail}", 5000)
                return

            # API cũ: res là path exe mới hoặc None
            if isinstance(res, (str, Path)) and res:
                new_path = Path(res)
                if sys.platform.startswith("win"):
                    ans = QMessageBox.question(
                        self, "Update ready",
                        f"A new version has been downloaded.\n\nLaunch the updated app now?\n\n{new_path}",
                        QMessageBox.Yes | QMessageBox.No
                    )
                    if ans == QMessageBox.Yes:
                        try:
                            subprocess.Popen([str(new_path)], close_fds=True)
                        finally:
                            QApplication.quit()
                    else:
                        open_with_default_app(new_path.parent)
                else:
                    QMessageBox.information(self, "Update downloaded", f"Downloaded to: {new_path}")
                    open_with_default_app(new_path.parent)
                return

            # Không có update
            if not silent:
                QMessageBox.information(self, "Updates", f"You're on the latest version (v{APP_VERSION}).")
            else:
                self.statusBar().showMessage("Up-to-date.", 3000)

        except SystemExit:
            raise
        except Exception as e:
            if silent:
                self.statusBar().showMessage(f'Update check failed: {e}', 5000)
            else:
                QMessageBox.warning(self, "Update failed", str(e))

    # ──────────────────────────────────────────────────────────────────────
    # Small helpers
    # ──────────────────────────────────────────────────────────────────────
    def _set_working_dir(self, path: Path) -> None:
        self.working_dir = path
        self.header_title.setText(f'Manuscript: {path.name}')
        self.working_label.setText(str(path))
        self._update_mapping_label()
        self.btn_refresh_inbox.setEnabled(True)
        self._refresh_history()
        self.refresh_inbox()

    def _update_mapping_label(self) -> None:
        if not self.working_dir:
            self.mapping_label.setText('Remote mapping: (none)')
            return
        m = get_mapping(self.working_dir)
        if m:
            root = m.get('students_root', '')
            who = m.get('student_name', '')
            slug = m.get('slug', '')
            self.mapping_label.setText(f'Remote: {root} → {who}/{slug}')
        else:
            self.mapping_label.setText('Remote mapping: (none)')

    def _fmt_time(self, ts: float) -> str:
        dt = datetime.fromtimestamp(ts)
        return dt.strftime('%Y-%m-%d %H:%M:%S')

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
        parent = QFileDialog.getExistingDirectory(self, 'Choose a parent directory for the manuscript')
        if not parent:
            return
        name, ok = QInputDialog.getText(self, 'Manuscript name', 'Enter a manuscript name (e.g. Paper 1):')
        if not ok or not name.strip():
            return
        journal, ok = QInputDialog.getText(self, 'Target journal (optional)', 'Enter target journal (optional):')
        if not ok:
            return

        slug = slugify(name)
        new_dir = Path(parent) / slug
        if new_dir.exists():
            QMessageBox.warning(self, 'Folder exists', f'The folder already exists:\n{new_dir}')
            return

        new_dir.mkdir(parents=True, exist_ok=True)
        write_minimal_paper_yaml(new_dir, title=name.strip(), journal=journal.strip())
        init_repo(new_dir)
        repo_commit(new_dir, message='Initial snapshot (auto)')

        self.statusBar().showMessage('Initialised new manuscript and repo.', 4000)
        self._set_working_dir(new_dir)

    def open_existing(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, 'Select manuscript folder')
        if not folder:
            return
        path = Path(folder)
        if not is_repo(path):
            resp = QMessageBox.question(
                self,
                'Initialise repository?',
                'This folder has no repository (.paperrepo). Do you want to initialise it now?',
                QMessageBox.Yes | QMessageBox.No,
            )
            if resp == QMessageBox.Yes:
                init_repo(path)
                repo_commit(path, message='Initial snapshot (auto)')
        self.statusBar().showMessage('Manuscript ready.', 3000)
        self._set_working_dir(path)

    # ──────────────────────────────────────────────────────────────────────
    # Commit / History / Restore
    # ──────────────────────────────────────────────────────────────────────
    def commit_snapshot(self) -> None:
        if not self.working_dir:
            QMessageBox.warning(self, 'No manuscript', 'Please select or create a manuscript folder first.')
            return
        if not is_repo(self.working_dir):
            init_repo(self.working_dir)

        message, ok = QInputDialog.getText(self, 'Commit message', 'Describe your changes:', text='Checkpoint')
        if not ok or not message.strip():
            return

        c = repo_commit(self.working_dir, message=message.strip())
        self.statusBar().showMessage(f'Committed {c.id[:7]} at {int(c.timestamp)}', 5000)
        self._refresh_history()

    def _refresh_history(self) -> None:
        self.history_list.clear()
        if not self.working_dir or not is_repo(self.working_dir):
            return
        commits = repo_history(self.working_dir)
        for i, c in enumerate(commits):
            title = c.message.splitlines()[0] if c.message else '(no message)'
            when = self._fmt_time(c.timestamp)
            text = f'{i + 1:02d} | {when} | {title} | {c.id[:12]}'
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
        box.setWindowTitle('Restore working copy')
        box.setText(
            'Do you want to CLEAN the working folder before restoring?\n\n'
            'Yes = Clean (remove existing files except .paperrepo etc.)\n'
            'No = Overlay (keep unrelated files, overwrite tracked ones)\n'
            'Cancel = abort.'
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
            QMessageBox.critical(self, 'Restore failed', str(e))
            return

        self.statusBar().showMessage(f'Restored {written} file(s) from {commit_id[:12]}', 6000)
        QMessageBox.information(self, 'Restored', f'Working copy restored to commit:\n{commit_id[:12]}')

    # ──────────────────────────────────────────────────────────────────────
    # Mapping / Inbox
    # ──────────────────────────────────────────────────────────────────────
    def change_remote_for_current(self) -> None:
        if not self.working_dir:
            QMessageBox.warning(self, 'No manuscript', 'Open a manuscript first.')
            return
        current = get_mapping(self.working_dir) or {}
        newmap = self._prompt_for_mapping(current)
        if newmap:
            self._update_mapping_label()
            self.btn_refresh_inbox.setEnabled(True)
            self.refresh_inbox()
            QMessageBox.information(
                self,
                'Mapping updated',
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
            self, 'Select Students’ Root (OneDrive)', dir=defaults.get('students_root') or '',
        )
        if not students_root_dir:
            return None

        student_name, ok = QInputDialog.getText(
            self, 'Student name', 'Enter your display name (as used by the supervisor):',
            text=defaults.get('student_name') or '',
        )
        if not ok or not student_name.strip():
            return None

        default_slug = slugify(self.working_dir.name)
        manuscript_slug, ok = QInputDialog.getText(
            self, 'Manuscript slug', 'Slug for this manuscript folder:', text=default_slug,
        )
        if not ok or not manuscript_slug.strip():
            return None
        manuscript_slug = slugify(manuscript_slug)

        remember_defaults(students_root_dir, student_name.strip())
        remember_mapping(self.working_dir, students_root_dir, student_name.strip(), manuscript_slug)

        return get_mapping(self.working_dir)

    def _prompt_for_mapping(self, preset: Optional[dict] = None) -> Optional[dict]:
        if not self.working_dir:
            QMessageBox.warning(self, 'No manuscript', 'Open a manuscript first.')
            return None

        defaults = get_defaults()
        start_dir = (preset or {}).get('students_root') or defaults.get('students_root') or ''
        students_root_dir = QFileDialog.getExistingDirectory(self, 'Select Students’ Root (OneDrive)', dir=start_dir)
        if not students_root_dir:
            return None

        student_name_default = (preset or {}).get('student_name') or defaults.get('student_name') or ''
        student_name, ok = QInputDialog.getText(
            self, 'Student name', 'Enter your display name (as used by the supervisor):', text=student_name_default,
        )
        if not ok or not student_name.strip():
            return None

        slug_default = (preset or {}).get('slug') or slugify(self.working_dir.name)
        manuscript_slug, ok = QInputDialog.getText(
            self, 'Manuscript slug', 'Slug for this manuscript folder:', text=slug_default,
        )
        if not ok or not manuscript_slug.strip():
            return None
        manuscript_slug = slugify(manuscript_slug)

        # Save
        remember_defaults(students_root_dir, student_name.strip())
        remember_mapping(self.working_dir, students_root_dir, student_name.strip(), manuscript_slug)

        return {'students_root': students_root_dir, 'student_name': student_name.strip(), 'slug': manuscript_slug}

    def _apply_inbox_filter(self) -> None:
        q = (self.inbox_filter.text() or '').strip().lower()
        for i in range(self.inbox_list.count()):
            it = self.inbox_list.item(i)
            it.setHidden(q not in it.text().lower())

    def refresh_inbox(self) -> None:
        self.inbox_list.clear()
        if self.comments_preview:
            self.comments_preview.clear()
            self.comments_preview.setPlaceholderText('No comments selected.')
        if not self.working_dir:
            return

        mapping = get_mapping(self.working_dir)
        if not mapping:
            self.btn_open_review.setEnabled(False)
            return

        students_root = Path(mapping['students_root'])
        student_name = mapping['student_name']
        slug = mapping['slug']

        mroot = students_root / student_name / slug
        reviews = mroot / 'reviews'
        if not reviews.exists():
            self.btn_open_review.setEnabled(False)
            return

        events_dir = mroot / 'events'
        count = 0

        for subdir in sorted(reviews.iterdir(), key=lambda p: p.name, reverse=True):
            if not subdir.is_dir():
                continue
            sub_id = subdir.name
            docx = subdir / 'returned.docx'
            doc = subdir / 'returned.doc'
            html = subdir / 'review.html'     # pre-return preview (latex)
            rhtml = subdir / 'returned.html'  # post-return (latex)

            target, label = None, None
            if docx.exists():
                target, label = docx, 'returned.docx'
            elif doc.exists():
                target, label = doc, 'returned.doc'
            elif rhtml.exists():
                target, label = rhtml, 'returned.html'
            elif html.exists():
                target, label = html, 'review.html'
            else:
                continue

            sub_ts, ret_ts = get_submission_times(events_dir, sub_id)
            when = f'submitted {iso_to_local_str(sub_ts)}'
            if ret_ts:
                when = f'returned {iso_to_local_str(ret_ts)}'

            item = QListWidgetItem(f'Submission {sub_id} — {label} · {when}', self.inbox_list)
            item.setData(Qt.UserRole, str(target))
            item.setData(Qt.UserRole + 1, sub_id)
            item.setData(Qt.UserRole + 2, str((target.parent / 'comments.json')))
            count += 1

        self.btn_open_review.setEnabled(count > 0)
        self._apply_inbox_filter()

    def open_selected_review(self) -> None:
        items = self.inbox_list.selectedItems()
        if not items:
            return
        path = Path(items[0].data(Qt.UserRole))
        if not path.exists():
            QMessageBox.warning(self, 'Missing file', f'Review file not found:\n{path}')
            return
        open_with_default_app(path)

    def pull_selected_review(self) -> None:
        if not self.working_dir:
            QMessageBox.warning(self, 'No manuscript', 'Please select or create a manuscript folder first.')
            return
        items = self.inbox_list.selectedItems()
        if not items:
            return

        src = Path(items[0].data(Qt.UserRole))
        sub_id = items[0].data(Qt.UserRole + 1) or 'unknown'
        if not src.exists():
            QMessageBox.warning(self, 'Missing file', f'Review file not found:\n{src}')
            return

        dest_dir = self.working_dir / 'received_reviews' / sub_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f'returned{src.suffix.lower()}'

        try:
            shutil.copy2(src, dest)
            comments = src.parent / 'comments.json'
            if comments.exists():
                shutil.copy2(comments, dest_dir / 'comments.json')
        except Exception as e:
            QMessageBox.critical(self, 'Save failed', str(e))
            return

        resp = QMessageBox.question(
            self,
            'Create checkpoint?',
            'A copy of the review has been saved locally.\n\n'
            'Do you want to create a checkpoint to record this in history?',
            QMessageBox.Yes | QMessageBox.No,
        )
        if resp == QMessageBox.Yes:
            try:
                repo_commit(self.working_dir, message=f'Save supervisor review for submission {sub_id}')
                self._refresh_history()
            except Exception:
                pass

        self.statusBar().showMessage(f'Saved review to: {dest}', 6000)
        QMessageBox.information(self, 'Saved', f'Review saved to:\n{dest}')

    def _load_comments_preview(self) -> None:
        if not self.comments_preview:
            return
        self.comments_preview.clear()
        items = self.inbox_list.selectedItems()
        if not items:
            self.comments_preview.setPlaceholderText('No comments selected.')
            return
        cpath = Path(items[0].data(Qt.UserRole + 2) or '')
        if not cpath.exists():
            self.comments_preview.setPlaceholderText('No comments.json found for this review.')
            return

        try:
            data = json.loads(cpath.read_text(encoding='utf-8'))
        except Exception as e:
            self.comments_preview.setPlainText(f'Failed to read comments.json:\n{e}')
            return

        general = (data.get('general') or '').strip()
        items_list = data.get('items') or []

        lines = []
        if general:
            lines += ['GENERAL NOTES', '-------------', general, '']
        if items_list:
            lines += ['ITEMISED COMMENTS', '-----------------']
            for i, it in enumerate(items_list, 1):
                f = it.get('file', '')
                ls = it.get('line_start', it.get('line', ''))
                le = it.get('line_end', ls)
                t = it.get('text', '')
                loc = f'{f}:{ls}' if ls == le else f'{f}:{ls}-{le}'
                lines.append(f'{i:02d}. {loc} — {t}')

        if not lines:
            self.comments_preview.setPlaceholderText('No comments in this review.')
        else:
            self.comments_preview.setPlainText('\n'.join(lines))

    # ──────────────────────────────────────────────────────────────────────
    # Submit
    # ──────────────────────────────────────────────────────────────────────
    def submit_to_supervisor(self) -> None:
        if not self.working_dir:
            QMessageBox.warning(self, 'No manuscript', 'Please select or create a manuscript folder first.')
            return

        if not head_commit_id(self.working_dir):
            repo_commit(self.working_dir, message='Initial snapshot (auto)')

        message, ok = QInputDialog.getText(self, 'Commit message', 'Message for this submission:', text='Work ready for review')
        if ok and message.strip():
            repo_commit(self.working_dir, message=message.strip())

        # Select mapping or create
        mapping = self._ensure_mapping()
        if not mapping:
            return

        students_root_dir = mapping['students_root']
        student_name = mapping['student_name']
        manuscript_slug = mapping['slug']

        dest_root = manuscript_root(Path(students_root_dir), student_name, manuscript_slug)
        subs = manuscript_subdirs(dest_root)

        # Create submission package
        submission_id = datetime.utcnow().strftime('%Y%m%d%H%M%S')  # stable id is fine here
        dest = subs['submissions'] / submission_id
        payload = dest / 'payload'
        payload.mkdir(parents=True, exist_ok=True)

        for p in self.working_dir.rglob('*'):
            if p.is_dir():
                continue
            rel = p.relative_to(self.working_dir)
            if any(part in {'.paperrepo', 'submissions', 'reviews', 'events'} for part in rel.parts):
                continue
            (payload / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, payload / rel)

        mtype = detect_manuscript_type(payload)

        # Read journal from paper.yaml if present
        journal_val = None
        try:
            paper_cfg = json.loads((self.working_dir / 'paper.yaml').read_text(encoding='utf-8'))
            journal_val = (paper_cfg.get('journal') or '').strip() or None
        except Exception:
            pass

        manifest = Manifest(
            manuscript_title=self.working_dir.name,
            manuscript_type=mtype,
            commit_id=(head_commit_id(self.working_dir) or ''),
            created_at=time(),
            student_name=student_name,
            manuscript_slug=manuscript_slug,
            notes=message if isinstance(message, str) else None,
            submitted_at=utcnow_iso(),
            journal=journal_val,
        )
        (dest / 'manifest.json').write_text(
            json.dumps(asdict(manifest), ensure_ascii=False, indent=2), encoding='utf-8'
        )

        write_event(subs['events'], new_submission_event(submission_id))
        self.statusBar().showMessage(f'Submission created: {submission_id}', 6000)
        QMessageBox.information(self, 'Submitted', f'Submission has been created:\n{submission_id}')

        self.refresh_inbox()

    # Save window state
    def closeEvent(self, ev):
        if hasattr(self, '_settings'):
            self._settings.setValue('geometry', self.saveGeometry())
            self._settings.setValue('state', self.saveState())
        super().closeEvent(ev)


# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    app = QApplication(sys.argv)
    window = StudentWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
