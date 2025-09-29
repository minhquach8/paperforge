from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSettings, QSize, Qt
from PySide6.QtGui import QAction, QKeySequence
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

# Local (refactor)
from apps.student_app.data import InboxItem
from apps.student_app.dialogs import prompt_due_datetime, prompt_mapping
from apps.student_app.scan import scan_inbox
from apps.student_app.services import (
    change_mapping,
    create_submission_package,
    ensure_mapping,
    ensure_repo_ready,
    open_review,
    pull_review_to_working,
    write_minimal_paper_yaml,
)

# Repo
from paperrepo.repo import commit as repo_commit
from paperrepo.repo import head_commit_id, init_repo, is_repo
from paperrepo.repo import history as repo_history
from paperrepo.repo import restore as repo_restore

# Shared
from shared.buildinfo import get_display_version, get_repo
from shared.config import get_mapping
from shared.due import is_overdue_iso, write_return_due
from shared.paths import slugify
from shared.ui.update_qt import check_for_updates
from shared.updater import cleanup_legacy_appdata_if_any

APP_NAME = "Paperforge — Student"

class StudentWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME); self.resize(1200, 820)

        # Toolbar
        tb = QToolBar("Quick actions", self); tb.setIconSize(QSize(18, 18)); tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon); self.addToolBar(tb)
        style = self.style(); std = style.standardIcon
        act_new = QAction(std(QStyle.SP_FileIcon), "New", self)
        act_open = QAction(std(QStyle.SP_DirOpenIcon), "Open", self)
        act_commit = QAction(std(QStyle.SP_DialogSaveButton), "Commit", self)
        act_submit = QAction(std(QStyle.SP_ArrowRight), "Submit", self)
        act_setroot = QAction(std(QStyle.SP_DirLinkIcon), "Set/Change Students’ Root…", self)
        act_hist = QAction(std(QStyle.SP_BrowserReload), "Refresh history", self)
        act_inbox = QAction(std(QStyle.SP_BrowserReload), "Refresh inbox", self)
        act_restore = QAction(std(QStyle.SP_DialogResetButton), "Restore…", self)
        act_update = QAction(std(QStyle.SP_BrowserReload), "Check for updates…", self)

        act_new.setShortcut(QKeySequence.New); act_open.setShortcut(QKeySequence.Open)
        act_commit.setShortcut(QKeySequence("Ctrl+S")); act_submit.setShortcut(QKeySequence("Ctrl+Return"))
        act_setroot.setShortcut(QKeySequence("Ctrl+Shift+L")); act_hist.setShortcut(QKeySequence("Shift+F5"))
        act_inbox.setShortcut(QKeySequence("F5")); act_restore.setShortcut(QKeySequence("Ctrl+R"))

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
        tb.addSeparator(); tb.addAction(act_update)

        # Central layout
        central = QWidget(self); outer = QVBoxLayout(central); outer.setContentsMargins(12, 8, 12, 12); outer.setSpacing(10)

        # Header card
        self.header_title = QLabel("Manuscript: (none)", self); self.header_title.setStyleSheet("font-size: 16px; font-weight: 600;")
        self.working_label = QLineEdit(self); self.working_label.setReadOnly(True); self.working_label.setPlaceholderText("Working folder: (none)")
        self.working_label.setStyleSheet("QLineEdit { background: #f7f7f7; }")
        self.mapping_label = QLabel("Remote mapping: (none)", self); self.mapping_label.setStyleSheet("color:#555;")
        header = QVBoxLayout(); header.addWidget(self.header_title); header.addWidget(self.working_label); header.addWidget(self.mapping_label)
        header_box = QGroupBox(""); header_box.setLayout(header); header_box.setStyleSheet("QGroupBox { border: 1px solid #e3e3e3; border-radius: 8px; margin-top: 4px; }")
        outer.addWidget(header_box)

        # Splitters
        split_main = QSplitter(Qt.Vertical, self)

        # History
        hist_box = QGroupBox("History (newest first)"); hist_layout = QHBoxLayout(hist_box)
        self.history_list = QListWidget(self); self.history_list.setSelectionMode(QAbstractItemView.SingleSelection); self.history_list.itemSelectionChanged.connect(self._on_history_selection)
        hist_btns = QVBoxLayout(); self.btn_refresh_hist = QPushButton("Refresh"); self.btn_restore = QPushButton("Restore to working copy…")
        self.btn_refresh_hist.clicked.connect(self._refresh_history); self.btn_restore.clicked.connect(self.restore_selected_commit)
        self.btn_restore.setEnabled(False); hist_btns.addWidget(self.btn_refresh_hist); hist_btns.addWidget(self.btn_restore); hist_btns.addStretch(1)
        hist_layout.addWidget(self.history_list, 1); hist_layout.addLayout(hist_btns)

        # Inbox + comments
        split_bottom = QSplitter(Qt.Horizontal, self)

        inbox_box = QGroupBox("Inbox — reviews returned by supervisor"); inbox_layout = QVBoxLayout(inbox_box)
        search_row = QHBoxLayout(); search_row.addWidget(QLabel("Filter:"))
        self.inbox_filter = QLineEdit(self); self.inbox_filter.setPlaceholderText("Search in submission id / filename / label"); self.inbox_filter.textChanged.connect(self._apply_inbox_filter)
        search_row.addWidget(self.inbox_filter); inbox_layout.addLayout(search_row)

        self.inbox_list = QListWidget(self); self.inbox_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.inbox_list.itemSelectionChanged.connect(self._on_inbox_selection); inbox_layout.addWidget(self.inbox_list, 1)

        inbox_btns = QHBoxLayout()
        self.btn_refresh_inbox = QPushButton("Refresh inbox")
        self.btn_open_review = QPushButton("Open selected review")
        self.btn_pull_review = QPushButton("Save a copy to working folder")
        self.btn_refresh_inbox.clicked.connect(self.refresh_inbox)
        self.btn_open_review.clicked.connect(self._open_selected_review)
        self.btn_pull_review.clicked.connect(self._pull_selected_review)
        self.btn_open_review.setEnabled(False); self.btn_pull_review.setEnabled(False)
        inbox_btns.addWidget(self.btn_refresh_inbox); inbox_btns.addStretch(1); inbox_btns.addWidget(self.btn_open_review); inbox_btns.addWidget(self.btn_pull_review)
        inbox_layout.addLayout(inbox_btns)

        comments_box = QGroupBox("Comments (read-only preview)"); comments_layout = QVBoxLayout(comments_box)
        self.comments_preview = QTextEdit(self); self.comments_preview.setReadOnly(True); self.comments_preview.setPlaceholderText("No comments selected.")
        comments_layout.addWidget(self.comments_preview)

        split_bottom.addWidget(inbox_box); split_bottom.addWidget(comments_box); split_bottom.setSizes([600, 600])
        split_main.addWidget(hist_box); split_main.addWidget(split_bottom); split_main.setSizes([350, 470])

        outer.addWidget(split_main, 1); self.setCentralWidget(central)

        # Footer
        credit = QLabel("Made by Minh Quach", self); credit.setStyleSheet("color:#666; margin-top:6px;")
        self.statusBar().addPermanentWidget(credit)
        self.lbl_ver = QLabel(f"v{get_display_version()}", self); self.lbl_ver.setStyleSheet("color:#666; margin-left:12px;")
        self.statusBar().addPermanentWidget(self.lbl_ver)

        # State
        self.working_dir: Optional[Path] = None
        self._current_mroot: Optional[Path] = None
        self.btn_refresh_inbox.setEnabled(False)

        self.setStyleSheet("""
            QListWidget { font-size: 13px; }
            QPushButton { padding: 6px 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
        """)

        self._settings = QSettings("Paperforge", "Student")
        if self._settings.value("geometry"): self.restoreGeometry(self._settings.value("geometry"))
        if self._settings.value("state"): self.restoreState(self._settings.value("state"))

        self.statusBar().showMessage("Ready", 3000)
        cleanup_legacy_appdata_if_any()

    # ── Updates
    def _check_updates(self) -> None:
        check_for_updates(self, app_id="student", repo=get_repo(), current_version=get_display_version(), app_keyword="Student")

    # ── Small helpers
    def _set_working_dir(self, path: Path) -> None:
        self.working_dir = path
        self.header_title.setText(f"Manuscript: {path.name}")
        self.working_label.setText(str(path))
        self._update_mapping_label()
        self.btn_refresh_inbox.setEnabled(True)
        self._refresh_history(); self.refresh_inbox()

    def _update_mapping_label(self) -> None:
        if not self.working_dir:
            self.mapping_label.setText("Remote mapping: (none)"); return
        m = get_mapping(self.working_dir)
        if m:
            self.mapping_label.setText(f"Remote: {m.get('students_root','')} → {m.get('student_name','')}/{m.get('slug','')}")
        else:
            self.mapping_label.setText("Remote mapping: (none)")

    def _on_history_selection(self) -> None:
        self.btn_restore.setEnabled(bool(self.history_list.selectedItems()))

    def _on_inbox_selection(self) -> None:
        has = bool(self.inbox_list.selectedItems())
        self.btn_open_review.setEnabled(has); self.btn_pull_review.setEnabled(has)
        self._load_comments_preview()

    # ── Create / Open
    def create_new(self) -> None:
        parent = QFileDialog.getExistingDirectory(self, 'Choose a parent directory for the manuscript')
        if not parent: return
        name, ok = QInputDialog.getText(self, 'Manuscript name', 'Enter a manuscript name (e.g. Paper 1):')
        if not ok or not name.strip(): return
        journal, ok = QInputDialog.getText(self, 'Target journal (optional)', 'Enter target journal (optional):')
        if not ok: return
        slug = slugify(name); new_dir = Path(parent) / slug
        if new_dir.exists() and any(new_dir.iterdir()):
            QMessageBox.warning(self, 'Folder exists', f'The folder already exists and is not empty:\n{new_dir}\n\nPlease choose another name or remove the folder.'); return
        new_dir.mkdir(parents=True, exist_ok=True)
        try: write_minimal_paper_yaml(new_dir, title=name.strip(), journal=journal.strip())
        except Exception as e: QMessageBox.critical(self, 'Error writing paper.yaml', str(e)); return
        try: init_repo(new_dir)
        except Exception as e: QMessageBox.critical(self, 'Init repository failed', f'Could not create repository at:\n{new_dir}\n\n{e}'); return
        if not is_repo(new_dir): QMessageBox.critical(self, 'Repository not found', f'Init succeeded but repo not detected at:\n{new_dir}'); return
        try:
            c = repo_commit(new_dir, message=f'Initial snapshot: {name.strip()}')
            self.statusBar().showMessage(f'Initialised repo and committed {c.id[:7]}', 4000)
        except Exception as e:
            QMessageBox.warning(self, 'Initial commit failed', f'Repository initialised but initial commit failed.\n\n{e}')
        self._set_working_dir(new_dir)
        QMessageBox.information(self, 'New manuscript', f'Created manuscript folder and repository:\n{new_dir}')

    def open_existing(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select manuscript folder")
        if not folder: return
        path = Path(folder)
        if is_repo(path):
            self.statusBar().showMessage("Manuscript ready.", 3000); self._set_working_dir(path); return
        child_repos = [d for d in path.iterdir() if d.is_dir() and is_repo(d)]
        if not child_repos:
            level2 = []
            for d1 in path.iterdir():
                if not d1.is_dir(): continue
                try:
                    for d2 in d1.iterdir():
                        if d2.is_dir() and is_repo(d2): level2.append(d2)
                except Exception: pass
            child_repos = level2
        if child_repos:
            if len(child_repos) == 1: chosen = child_repos[0]
            else:
                names = [str(p) for p in child_repos]
                chosen_str, ok = QInputDialog.getItem(self, "Choose manuscript", "This folder has no repository.\nSelect a manuscript inside:", names, 0, False)
                if not ok or not chosen_str: return
                chosen = Path(chosen_str)
            self.statusBar().showMessage(f"Opening nested manuscript: {chosen}", 4000); self._set_working_dir(chosen); return

        resp = QMessageBox.question(self, "Initialise repository?", "This folder has no repository (.paperrepo). Do you want to initialise it now?", QMessageBox.Yes | QMessageBox.No)
        if resp == QMessageBox.Yes:
            try:
                init_repo(path); repo_commit(path, message="Initial snapshot (auto)")
            except Exception as e:
                QMessageBox.critical(self, "Init repository failed", str(e)); return
            self.statusBar().showMessage("Repository initialised.", 3000); self._set_working_dir(path)

    # ── Commit / History / Restore
    def commit_snapshot(self) -> None:
        if not self.working_dir:
            QMessageBox.warning(self, "No manuscript", "Please select or create a manuscript folder first."); return
        if not is_repo(self.working_dir): init_repo(self.working_dir)
        message, ok = QInputDialog.getText(self, "Commit message", "Describe your changes:", text="Checkpoint")
        if not ok or not message.strip(): return
        c = repo_commit(self.working_dir, message=message.strip())
        self.statusBar().showMessage(f"Committed {c.id[:7]} at {int(c.timestamp)}", 5000); self._refresh_history()

    def _refresh_history(self) -> None:
        self.history_list.clear()
        if not self.working_dir or not is_repo(self.working_dir): return
        commits = repo_history(self.working_dir)
        from datetime import datetime as _dt
        for i, c in enumerate(commits):
            title = c.message.splitlines()[0] if c.message else "(no message)"
            when = _dt.fromtimestamp(c.timestamp).strftime("%Y-%m-%d %H:%M:%S")
            text = f"{i + 1:02d} | {when} | {title} | {c.id[:12]}"
            it = QListWidgetItem(text, self.history_list); it.setData(Qt.UserRole, c.id)

    def restore_selected_commit(self) -> None:
        if not self.working_dir: return
        items = self.history_list.selectedItems()
        if not items: return
        commit_id = items[0].data(Qt.UserRole)
        box = QMessageBox(self); box.setWindowTitle("Restore working copy")
        box.setText("Do you want to CLEAN the working folder before restoring?\n\nYes = Clean (remove existing files except .paperrepo etc.)\nNo = Overlay (keep unrelated files, overwrite tracked ones)\nCancel = abort.")
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel); box.setDefaultButton(QMessageBox.No)
        resp = box.exec()
        if resp == QMessageBox.Cancel: return
        clean = resp == QMessageBox.Yes
        try:
            written = repo_restore(self.working_dir, commit_id=commit_id, clean=clean)
        except Exception as e:
            QMessageBox.critical(self, "Restore failed", str(e)); return
        self.statusBar().showMessage(f"Restored {written} file(s) from {commit_id[:12]}", 6000)
        QMessageBox.information(self, "Restored", f"Working copy restored to commit:\n{commit_id[:12]}")

    # ── Mapping / Inbox
    def change_remote_for_current(self) -> None:
        if not self.working_dir:
            QMessageBox.warning(self, "No manuscript", "Open a manuscript first."); return
        newmap = change_mapping(self, self.working_dir)
        if newmap:
            self._update_mapping_label(); self.btn_refresh_inbox.setEnabled(True); self.refresh_inbox()
            QMessageBox.information(self, "Mapping updated", f'Now linked to:\n{newmap["students_root"]}\n{newmap["student_name"]}/{newmap["slug"]}')

    def _apply_inbox_filter(self) -> None:
        q = (self.inbox_filter.text() or "").strip().lower()
        for i in range(self.inbox_list.count()):
            it = self.inbox_list.item(i)
            it.setHidden(q not in it.text().lower())

    def refresh_inbox(self) -> None:
        self.inbox_list.clear()
        if self.comments_preview:
            self.comments_preview.clear(); self.comments_preview.setPlaceholderText("No comments selected.")
        if not self.working_dir: return
        mapping = get_mapping(self.working_dir)
        if not mapping:
            self.btn_open_review.setEnabled(False); return
        from shared.paths import manuscript_root as _mr
        mroot = _mr(Path(mapping["students_root"]), mapping["student_name"], mapping["slug"])
        self._current_mroot = mroot
        rows = scan_inbox(mroot)
        count = 0
        for row in rows:
            text = f"Submission {row.sub_id} — {row.label}"
            if row.when_label: text += f" · {row.when_label}"
            if row.due_label:  text += f" · due: {row.due_label}"
            it = QListWidgetItem(text, self.inbox_list)
            it.setData(Qt.UserRole, row)  # store whole InboxItem
            if row.overdue:
                from PySide6.QtGui import QBrush, QColor, QFont
                it.setForeground(QBrush(QColor("#B00020"))); f = QFont(self.font()); f.setBold(True); it.setFont(f)
            count += 1
        self.btn_open_review.setEnabled(count > 0); self._apply_inbox_filter()

    def _open_selected_review(self) -> None:
        items = self.inbox_list.selectedItems()
        if not items: return
        row: InboxItem = items[0].data(Qt.UserRole)
        open_review(self, row)

    def _pull_selected_review(self) -> None:
        if not self.working_dir:
            QMessageBox.warning(self, "No manuscript", "Please select or create a manuscript folder first."); return
        items = self.inbox_list.selectedItems()
        if not items: return
        row: InboxItem = items[0].data(Qt.UserRole)
        pull_review_to_working(self, self.working_dir, row)

    def _load_comments_preview(self) -> None:
        self.comments_preview.clear()
        items = self.inbox_list.selectedItems()
        if not items:
            self.comments_preview.setPlaceholderText("No comments selected."); return
        row: InboxItem = items[0].data(Qt.UserRole)
        cpath = row.comments_json
        if not cpath.exists():
            self.comments_preview.setPlaceholderText("No comments.json found for this review."); return
        try:
            data = json.loads(cpath.read_text(encoding="utf-8"))
        except Exception as e:
            self.comments_preview.setPlainText(f"Failed to read comments.json:\n{e}"); return
        general = (data.get("general") or "").strip()
        items_list = data.get("items") or []
        lines = []
        if general: lines += ["GENERAL NOTES", "-------------", general, ""]
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

    # ── Submit (with CANCEL fix)
    def submit_to_supervisor(self) -> None:
        if not self.working_dir:
            QMessageBox.warning(self, "No manuscript", "Please select or create a manuscript folder first."); return

        # ensure repo & at least one commit
        try:
            ensure_repo_ready(self.working_dir)
        except Exception:
            # best-effort – ignore
            pass

        # Ask message (Cancel ==> STOP)
        message, ok = QInputDialog.getText(self, "Commit message", "Message for this submission:", text="Work ready for review")
        if not ok:
            self.statusBar().showMessage("Submission cancelled.", 4000); return
        if message and message.strip():
            repo_commit(self.working_dir, message=message.strip())

        # mapping (Cancel flow respected)
        mapping = ensure_mapping(self, self.working_dir)
        if not mapping:
            self.statusBar().showMessage("Submission cancelled (no mapping).", 4000); return

        dest_root, submission_id = create_submission_package(self, self.working_dir, mapping, message)
        QMessageBox.information(self, "Submitted", f"Submission has been created:\n{submission_id}")

        # optional expected date
        ask = QMessageBox.question(self, "Expected date (optional)",
                                   "Do you want to set your expected date to send back the revision for this submission now?",
                                   QMessageBox.Yes | QMessageBox.No)
        if ask == QMessageBox.Yes:
            iso, note = prompt_due_datetime(self)
            if iso:
                try:
                    write_return_due(dest_root, submission_id, iso, note=note, set_by="student")
                    self.statusBar().showMessage("Expected date saved.", 4000)
                except Exception as e:
                    QMessageBox.warning(self, "Set expected date failed", str(e))
        self.refresh_inbox()

    # Save window state
    def closeEvent(self, ev):
        if hasattr(self, "_settings"):
            self._settings.setValue("geometry", self.saveGeometry()); self._settings.setValue("state", self.saveState())
        super().closeEvent(ev)

def main() -> None:
    app = QApplication(sys.argv)
    window = StudentWindow(); window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
