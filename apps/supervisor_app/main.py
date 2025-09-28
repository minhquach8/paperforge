from __future__ import annotations

import html
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSettings, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStyle,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from apps.supervisor_app.latex_workspace import (
    LatexWorkspace,
    load_comments_json,
    save_comments_json,
)
from shared.config import load_config, save_config
from shared.events import get_submission_times, returned_event, write_event
from shared.latex.builder import build_pdf, detect_main_tex
from shared.latex.diff import build_diff_pdf
from shared.timeutil import iso_to_local_str

# ⬇️ Updater (portable) – tương thích cả API cũ/lẫn mới
from shared.updater import cleanup_legacy_appdata_if_any, download_and_stage_update
from shared.version import APP_VERSION

APP_NAME = 'Paperforge — Supervisor'
RECENTS_KEY = 'supervisor_recent_roots'
MAX_RECENTS = 5

STATUS_COLOURS = {
    'New': ('#E8F0FE', '#0B57D0'),
    'In review': ('#FFF8E1', '#8C6D1F'),
    'Returned': ('#E6F4EA', '#0F6D31'),
}

# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────
def open_with_default_app(path: Path) -> None:
    if sys.platform.startswith('win'):
        import os
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == 'darwin':
        subprocess.run(['open', str(path)], check=False)
    else:
        subprocess.run(['xdg-open', str(path)], check=False)


def detect_type_from_payload(root: Path) -> str:
    has_docx = any(p.is_file() and p.suffix.lower() == '.docx' for p in root.rglob('*'))
    has_doc = any(p.is_file() and p.suffix.lower() == '.doc' for p in root.rglob('*'))
    has_tex = any(p.is_file() and p.suffix.lower() == '.tex' for p in root.rglob('*'))
    has_word = has_docx or has_doc
    if has_word and not has_tex:
        return 'docx'
    if has_tex and not has_word:
        return 'latex'
    if has_word and has_tex:
        return 'docx'
    return 'docx'


def submission_status(manuscript_root: Path, submission_id: str) -> str:
    reviews_dir = manuscript_root / 'reviews' / submission_id
    if (
        (reviews_dir / 'returned.docx').exists()
        or (reviews_dir / 'returned.doc').exists()
        or (reviews_dir / 'returned.html').exists()
    ):
        return 'Returned'
    if (
        (reviews_dir / 'working.docx').exists()
        or (reviews_dir / 'working.doc').exists()
        or (reviews_dir / 'review.html').exists()
        or (reviews_dir / 'compiled.pdf').exists()
        or (reviews_dir / 'compiled_diff.pdf').exists()
    ):
        return 'In review'
    return 'New'


def write_latex_review_html(
    dst: Path,
    title: str,
    has_pdf: bool,
    pdf_path: Optional[Path],
    build_log: str,
    payload: Path,
    comments: Optional[dict] = None,
) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    log_escaped = html.escape(build_log or '', quote=False)
    tex_files = '\n'.join(
        f'<li>{html.escape(str(p.relative_to(payload)))}</li>'
        for p in sorted(payload.rglob('*.tex'))
    )
    pdf_block = ''
    if has_pdf and pdf_path and pdf_path.exists():
        pdf_rel = html.escape(pdf_path.name)
        pdf_block = f"""
        <p><a href="{pdf_rel}">Open {pdf_rel}</a></p>
        <embed src="{pdf_rel}" type="application/pdf" width="100%" height="800px"/>
        """

    comments_block = ''
    if comments:
        general = html.escape(comments.get('general', '') or '')
        items_html = ''
        for it in comments.get('items', []):
            file_ = html.escape(str(it.get('file', '')))
            ls = it.get('line_start', it.get('line', ''))
            le = it.get('line_end', ls)
            rng = f'{ls}-{le}' if (ls and le and ls != le) else f'{ls}'
            text_ = html.escape(str(it.get('text', '')))
            items_html += f'<li><code>{file_}:{rng}</code> — {text_}</li>\n'
        comments_block = f"""
        <details open>
          <summary><strong>Comments</strong></summary>
          <h4>General notes</h4>
          <pre>{general}</pre>
          <h4>Itemised</h4>
          <ul>
            {items_html}
          </ul>
        </details>
        """

    html_text = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>LaTeX Review – {html.escape(title)}</title>
  <style>
    body {{ font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 24px; }}
    h1 {{ margin-bottom: 8px; }}
    code, pre {{ background: #f5f5f5; padding: 8px; border-radius: 6px; }}
    details {{ margin-top: 16px; }}
  </style>
</head>
<body>
  <h1>LaTeX Review — {html.escape(title)}</h1>
  {pdf_block}
  {comments_block}
  <details>
    <summary><strong>Build log</strong></summary>
    <pre>{log_escaped}</pre>
  </details>
  <details>
    <summary><strong>Source files (.tex)</strong></summary>
    <ul>
      {tex_files}
    </ul>
  </details>
  <p><em>Generated by Supervisor app (MVP).</em></p>
</body>
</html>
"""
    dst.write_text(html_text, encoding='utf-8')


def last_review_edit_iso(manuscript_root: Path, submission_id: str) -> Optional[str]:
    rdir = manuscript_root / 'reviews' / submission_id
    if not rdir.exists():
        return None

    mtimes: list[float] = []

    def _add(p: Path) -> None:
        if p.exists():
            try:
                mtimes.append(p.stat().st_mtime)
            except Exception:
                pass

    for name in (
        'working.docx',
        'working.doc',
        'returned.docx',
        'returned.doc',
        'review.html',
        'returned.html',
        'compiled.pdf',
        'compiled_diff.pdf',
        'comments.json',
    ):
        _add(rdir / name)

    for sub in ('worktree', 'diff'):
        d = rdir / sub
        if d.exists():
            for p in d.rglob('*'):
                if p.is_file():
                    _add(p)

    if not mtimes:
        return None

    latest = max(mtimes)
    return (
        datetime.fromtimestamp(latest, tz=timezone.utc)
        .isoformat(timespec='minutes')
        .replace('+00:00', 'Z')
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main window
# ─────────────────────────────────────────────────────────────────────────────
class SupervisorWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1300, 860)

        central = QWidget(self)
        root = QVBoxLayout(central)

        # Toolbar
        tb = QToolBar('Quick actions', self)
        tb.setIconSize(QSize(18, 18))
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(tb)

        def _act(icon, text, slot, checkable=False):
            a = QAction(self.style().standardIcon(icon), text, self)
            a.setCheckable(checkable)
            a.triggered.connect(slot)
            tb.addAction(a)
            return a

        _act(QStyle.SP_DirOpenIcon, 'Choose Students’ Root…', self.choose_root)
        _act(QStyle.SP_BrowserReload, 'Scan', self.scan_root)
        tb.addSeparator()
        _act(QStyle.SP_ArrowDown, 'Expand all', lambda: self.tree.expandAll())
        _act(QStyle.SP_ArrowUp, 'Collapse all', lambda: self.tree.collapseAll())
        tb.addSeparator()
        _act(QStyle.SP_DialogResetButton, 'Clear filters', self._clear_filters)
        tb.addSeparator()
        self.act_autorescan = _act(
            QStyle.SP_BrowserReload, 'Auto-rescan', self._toggle_autorescan, checkable=True
        )
        tb.addSeparator()
        self.act_check_update = _act(
            QStyle.SP_BrowserReload, f'Check for updates… (v{APP_VERSION})', self._check_updates
        )

        # Current root label
        self.lbl_root = QLabel('Students’ Root: (none)', self)
        self.lbl_root.setStyleSheet('color:#444;')
        self.lbl_root.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self.lbl_root)

        # Recent roots row
        recent_row = QHBoxLayout()
        recent_row.addWidget(QLabel('Recent:'))
        self.cb_recent = QComboBox(self)
        self.cb_recent.setEditable(False)
        self.btn_use_recent = QPushButton('Open')
        self.btn_clear_recent = QPushButton('Clear')
        self.btn_use_recent.clicked.connect(self._use_selected_recent)
        self.btn_clear_recent.clicked.connect(self._clear_recents)
        self.cb_recent.activated.connect(lambda _ix: self._use_selected_recent())
        recent_row.addWidget(self.cb_recent, stretch=1)
        recent_row.addWidget(self.btn_use_recent)
        recent_row.addWidget(self.btn_clear_recent)
        root.addLayout(recent_row)

        # Filters
        filters = QHBoxLayout()
        filters.addWidget(QLabel('Search:'))
        self.ed_search = QLineEdit(self)
        self.ed_search.setPlaceholderText('Student / Manuscript / Journal / Submission ID')
        self.ed_search.setClearButtonEnabled(True)
        self.ed_search.textChanged.connect(self.scan_root)
        filters.addWidget(self.ed_search, stretch=1)

        filters.addWidget(QLabel('Status:'))
        self.cb_status = QComboBox(self)
        self.cb_status.addItems(['All', 'New', 'In review', 'Returned'])
        self.cb_status.currentIndexChanged.connect(self.scan_root)
        filters.addWidget(self.cb_status)

        filters.addWidget(QLabel('Type:'))
        self.cb_type = QComboBox(self)
        self.cb_type.addItems(['All', 'Word', 'LaTeX'])
        self.cb_type.currentIndexChanged.connect(self.scan_root)
        filters.addWidget(self.cb_type)

        root.addLayout(filters)

        # Legend
        legend = QLabel(
            'Legend: '
            '<span style="background:#E8F0FE;border:1px solid #9EB7F6;padding:2px 8px;border-radius:6px;">New</span> '
            '<span style="background:#FFF8E1;border:1px solid #E7D390;padding:2px 8px;border-radius:6px;">In review</span> '
            '<span style="background:#E6F4EA;border:1px solid #9CD3B0;padding:2px 8px;border-radius:6px;">Returned</span>'
        )
        legend.setStyleSheet('color:#444;')
        root.addWidget(legend)

        # Tree
        self.tree = QTreeWidget(self)
        self.tree.setColumnCount(8)
        self.tree.setHeaderLabels([
            'Student', 'Manuscript', 'Journal', 'Submission', 'Type', 'Status', 'When', 'Last Edit',
        ])
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.setUniformRowHeights(True)
        self.tree.itemDoubleClicked.connect(self._open_item)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSortingEnabled(True)
        self.tree.sortByColumn(0, Qt.AscendingOrder)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_tree_menu)
        root.addWidget(self.tree, stretch=1)

        # Action buttons
        actions = QHBoxLayout()
        self.btn_open = QPushButton('Open')
        self.btn_notes = QPushButton('Review notes…')
        self.btn_return = QPushButton('Return selected')
        self.btn_open.clicked.connect(self._open_selected)
        self.btn_notes.clicked.connect(self._open_notes_dialog)
        self.btn_return.clicked.connect(self._return_selected_batch)
        actions.addWidget(self.btn_open)
        actions.addWidget(self.btn_notes)
        actions.addWidget(self.btn_return)
        root.addLayout(actions)

        self.students_root: Optional[Path] = None
        self._update_recent_ui()

        # Auto-use most recent
        recents = self._load_recent_roots()
        if recents and Path(recents[0]).exists():
            self._set_students_root(Path(recents[0]), remember=False, autoscan=True)

        # Credit
        credit = QLabel('Made by Minh Quach', self)
        credit.setStyleSheet('color:#666; padding-left:12px;')
        self.statusBar().addPermanentWidget(credit)

        # Save/restore window state
        self._settings = QSettings('Paperforge', 'Supervisor')
        if self._settings.value('geometry'):
            self.restoreGeometry(self._settings.value('geometry'))
        if self._settings.value('state'):
            self.restoreState(self._settings.value('state'))

        # Auto-rescan timer
        self._timer = QTimer(self)
        self._timer.setInterval(90_000)
        self._timer.timeout.connect(self.scan_root)

        self.setCentralWidget(central)
        self.statusBar().showMessage('Ready', 3000)

        # Dọn cơ chế cũ nếu từng xài AppData
        cleanup_legacy_appdata_if_any()
        # Silent update check sau 3s
        QTimer.singleShot(3000, self._check_updates_silent)

    # ──────────────────────────────────────────────────────────────────────
    # Updates (manual & silent)
    # ──────────────────────────────────────────────────────────────────────
    def _check_updates(self) -> None:
        self._do_check_update(silent=False)

    def _check_updates_silent(self) -> None:
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

            # Thử gọi theo API cũ trước (4 tham số). Nếu TypeError ⇒ API mới.
            res = None
            try:
                # API cũ: trả path exe mới (hoặc None)
                from shared.version import GITHUB_REPO  # chỉ cần khi API cũ
                res = download_and_stage_update(GITHUB_REPO, "Supervisor", APP_VERSION, app_id="supervisor")
            except TypeError:
                # API mới: trả tuple(status, detail)
                res = download_and_stage_update("supervisor")

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
                    # Với updater mới, quá trình đã sinh batch & sẽ thoát app.
                    # Nếu chưa thoát (tuỳ implementation), thì thoát để batch chạy.
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
            # Updater mới có thể tự sys.exit(0) sau khi stage; cứ để thoát.
            raise
        except Exception as e:
            if silent:
                self.statusBar().showMessage(f'Update check failed: {e}', 5000)
            else:
                QMessageBox.warning(self, "Update failed", str(e))

    # ──────────────────────────────────────────────────────────────────────
    # Recents & root helpers
    # ──────────────────────────────────────────────────────────────────────
    def _update_root_label(self) -> None:
        txt = str(self.students_root) if self.students_root else '(none)'
        self.lbl_root.setText(f'Students’ Root: {txt}')

    def _set_students_root(self, path: Path, *, remember: bool = True, autoscan: bool = True) -> None:
        self.students_root = path
        self._update_root_label()
        if remember:
            self._remember_root(path)
        if autoscan:
            self.scan_root()

    def _load_recent_roots(self) -> list[str]:
        cfg = load_config()
        roots = cfg.get(RECENTS_KEY, [])
        if not isinstance(roots, list):
            roots = []
        out: list[str] = []
        seen = set()
        for r in roots:
            if not isinstance(r, str):
                continue
            if r in seen:
                continue
            if Path(r).exists():
                out.append(r); seen.add(r)
        return out

    def _save_recent_roots(self, roots: list[str]) -> None:
        cfg = load_config(); cfg[RECENTS_KEY] = roots[:MAX_RECENTS]; save_config(cfg)

    def _remember_root(self, path: Path) -> None:
        s = str(path)
        roots = self._load_recent_roots()
        roots = [r for r in roots if r != s]
        roots.insert(0, s)
        self._save_recent_roots(roots)
        self._update_recent_ui()

    def _update_recent_ui(self) -> None:
        roots = self._load_recent_roots()
        self.cb_recent.blockSignals(True)
        self.cb_recent.clear()
        for r in roots:
            self.cb_recent.addItem(r)
        self.cb_recent.blockSignals(False)
        enabled = bool(roots)
        self.btn_use_recent.setEnabled(enabled)
        self.btn_clear_recent.setEnabled(enabled)

    def _use_selected_recent(self) -> None:
        text = (self.cb_recent.currentText() or '').strip()
        if not text:
            return
        p = Path(text)
        if not p.exists():
            QMessageBox.warning(self, 'Not found', f'Folder no longer exists:\n{text}')
            roots = [r for r in self._load_recent_roots() if r != text]
            self._save_recent_roots(roots)
            self._update_recent_ui()
            return
        self._set_students_root(p, remember=True, autoscan=True)

    def _clear_recents(self) -> None:
        self._save_recent_roots([])
        self._update_recent_ui()

    # ──────────────────────────────────────────────────────────────────────
    # Root selection & scanning
    # ──────────────────────────────────────────────────────────────────────
    def choose_root(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, 'Select Students’ Root (OneDrive)')
        if folder:
            self._set_students_root(Path(folder), remember=True, autoscan=True)

    def _row_passes_filters(self, student: str, title: str, journal: str, sub_id: str, mtype: str, status: str) -> bool:
        q = self.ed_search.text().strip().lower()
        if q:
            if all(q not in s for s in (student.lower(), title.lower(), (journal or '').lower(), sub_id.lower())):
                return False
        ty = self.cb_type.currentText()
        if ty == 'Word' and mtype != 'docx':
            return False
        if ty == 'LaTeX' and mtype != 'latex':
            return False
        st = self.cb_status.currentText()
        if st != 'All' and status != st:
            return False
        return True

    def scan_root(self) -> None:
        self.tree.clear()
        if not self.students_root:
            return

        root = self.students_root
        total = 0

        for student_dir in sorted(root.iterdir()):
            if not student_dir.is_dir():
                continue

            student_node = QTreeWidgetItem([student_dir.name] + [''] * 7)
            student_node.setFirstColumnSpanned(True)
            student_has_rows = False
            student_count = 0

            for manuscript_dir in sorted(student_dir.iterdir()):
                if not manuscript_dir.is_dir():
                    continue
                submissions = manuscript_dir / 'submissions'
                if not submissions.exists():
                    continue

                title_default = manuscript_dir.name

                for subdir in sorted(submissions.iterdir()):
                    if not subdir.is_dir():
                        continue
                    manifest_path = subdir / 'manifest.json'
                    if not manifest_path.exists():
                        continue

                    payload = subdir / 'payload'

                    title = title_default
                    mtype = 'unknown'
                    journal = ''
                    try:
                        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
                        title = manifest.get('manuscript_title', title)
                        mtype = manifest.get('manuscript_type', 'unknown')
                        journal = (manifest.get('journal') or '').strip()
                    except Exception:
                        pass
                    if not journal:
                        try:
                            py = json.loads((payload / 'paper.yaml').read_text(encoding='utf-8'))
                            journal = (py.get('journal') or '').strip()
                        except Exception:
                            journal = ''

                    effective = detect_type_from_payload(payload)
                    if mtype != effective:
                        mtype = effective

                    status = submission_status(manuscript_dir, subdir.name)
                    events_dir = manuscript_dir / 'events'
                    sub_ts, ret_ts = get_submission_times(events_dir, subdir.name)
                    if not sub_ts:
                        try:
                            _mf = json.loads(manifest_path.read_text(encoding='utf-8'))
                            sub_ts = _mf.get('submitted_at')
                        except Exception:
                            pass

                    when_label = ''
                    if ret_ts or sub_ts:
                        label = 'returned' if ret_ts else 'submitted'
                        when_label = f'{label} {iso_to_local_str(ret_ts or sub_ts)}'

                    last_edit_iso = last_review_edit_iso(manuscript_dir, subdir.name)
                    last_edit_label = iso_to_local_str(last_edit_iso)

                    if not self._row_passes_filters(student_dir.name, title, journal, subdir.name, mtype, status):
                        continue

                    type_label = 'Word' if mtype == 'docx' else ('LaTeX' if mtype == 'latex' else mtype)
                    row = QTreeWidgetItem([
                        student_dir.name, title, journal, subdir.name, type_label, status, when_label, last_edit_label,
                    ])
                    self._apply_status_style(row, status)
                    row.setData(0, Qt.UserRole, str(subdir))

                    tips = []
                    if journal:
                        tips.append(f'Journal:  {journal}')
                    if sub_ts:
                        tips.append(f'Submitted: {iso_to_local_str(sub_ts)}')
                    if ret_ts:
                        tips.append(f'Returned:  {iso_to_local_str(ret_ts)}')
                    if last_edit_iso:
                        tips.append(f'Last edit: {iso_to_local_str(last_edit_iso)}')
                    if tips:
                        for col in range(self.tree.columnCount()):
                            row.setToolTip(col, '\n'.join(tips))

                    student_node.addChild(row)
                    student_has_rows = True
                    total += 1
                    student_count += 1

            if student_has_rows:
                student_node.setText(0, f'{student_dir.name}   ({student_count})')
                self.tree.addTopLevelItem(student_node)
                student_node.setExpanded(True)

        for col in (0, 1, 2, 4, 5, 7):
            self.tree.resizeColumnToContents(col)

        self.statusBar().showMessage(f'Found {total} submission(s) after filters.', 5000)

    # ──────────────────────────────────────────────────────────────────────
    # Item helpers
    # ──────────────────────────────────────────────────────────────────────
    def _selected_submission_dirs(self) -> list[Path]:
        out: list[Path] = []
        for item in self.tree.selectedItems():
            data = item.data(0, Qt.UserRole)
            if not data:
                continue
            p = Path(str(data))
            if p.exists():
                out.append(p)
        return out

    def _open_item(self, item: QTreeWidgetItem, _col: int) -> None:
        if not item.data(0, Qt.UserRole):
            if item.childCount():
                self._open_path(Path(item.child(0).data(0, Qt.UserRole)))
            return
        self._open_path(Path(item.data(0, Qt.UserRole)))

    def _open_selected(self) -> None:
        dirs = self._selected_submission_dirs()
        if not dirs:
            return
        self._open_path(dirs[0])

    def _open_path(self, subdir: Path) -> None:
        manifest_path = subdir / 'manifest.json'
        if not manifest_path.exists():
            QMessageBox.warning(self, 'Missing manifest', 'This submission has no manifest.json.')
            return

        payload = subdir / 'payload'
        mtype = detect_type_from_payload(payload)

        manuscript_root = subdir.parent.parent
        reviews_dir = manuscript_root / 'reviews' / subdir.name
        reviews_dir.mkdir(parents=True, exist_ok=True)

        if mtype == 'docx':
            primary = self._find_primary_word(payload)
            if not primary:
                QMessageBox.warning(self, 'No Word file', 'No .docx or .doc file was found in this submission.')
                return
            working = reviews_dir / f'working{primary.suffix.lower()}'
            shutil.copy2(primary, working)
            open_with_default_app(working)
            self.statusBar().showMessage('Opened working copy.', 4000)
            self.scan_root()
        elif mtype == 'latex':
            dlg = LatexWorkspace(self, submission_dir=subdir, reviews_dir=reviews_dir)
            dlg.exec()
            self.scan_root()
        else:
            QMessageBox.information(self, 'Unknown type', f'Manuscript type: {mtype}')

    def _find_primary_word(self, payload_dir: Path) -> Optional[Path]:
        for ext in ('.docx', '.doc'):
            for p in sorted(payload_dir.rglob(f'*{ext}')):
                return p
        return None

    def _apply_status_style(self, item: QTreeWidgetItem, status: str) -> None:
        colours = STATUS_COLOURS.get(status)
        if not colours:
            return
        bg_hex, fg_hex = colours
        bg = QBrush(QColor(bg_hex))
        fg = QBrush(QColor(fg_hex))
        for col in range(self.tree.columnCount()):
            item.setBackground(col, bg)
            item.setForeground(col, fg)
        f = QFont(self.font()); f.setBold(True)
        item.setFont(5, f)

    # ──────────────────────────────────────────────────────────────────────
    # Review notes & Return
    # ──────────────────────────────────────────────────────────────────────
    def _open_notes_dialog(self) -> None:
        dirs = self._selected_submission_dirs()
        if not dirs:
            return
        if len(dirs) > 1:
            QMessageBox.information(self, 'Notes', 'Please select a single submission to edit notes.')
            return

        subdir = dirs[0]
        manuscript_root = subdir.parent.parent
        reviews_dir = manuscript_root / 'reviews' / subdir.name
        reviews_dir.mkdir(parents=True, exist_ok=True)
        payload_dir = subdir / 'payload'

        if detect_type_from_payload(payload_dir) == 'latex':
            dlg = LatexWorkspace(self, submission_dir=subdir, reviews_dir=reviews_dir)
            dlg.exec()
            self.statusBar().showMessage('Workspace closed.', 3000)
            return

        data = load_comments_json(reviews_dir)
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTextEdit, QVBoxLayout
        d = QDialog(self)
        d.setWindowTitle('Review notes')
        lay = QVBoxLayout(d)
        ed = QTextEdit(d); ed.setPlainText(data.get('general', ''))
        lay.addWidget(QLabel('General notes:'))
        lay.addWidget(ed)
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel, parent=d)
        lay.addWidget(btns)

        def _save():
            data['general'] = ed.toPlainText()
            save_comments_json(reviews_dir, data)
            d.accept()

        btns.accepted.connect(_save)
        btns.rejected.connect(d.reject)
        d.exec()
        self.statusBar().showMessage('Comments saved.', 3000)

    def _return_selected_batch(self) -> None:
        dirs = self._selected_submission_dirs()
        if not dirs:
            QMessageBox.information(self, 'Return', 'Please select one or more submissions.')
            return

        successes = 0
        failures: list[str] = []
        for subdir in dirs:
            try:
                ok = self._return_one(subdir)
                if ok:
                    successes += 1
                else:
                    failures.append(subdir.name)
            except Exception as e:
                failures.append(f'{subdir.name} ({e})')

        self.scan_root()
        if failures:
            QMessageBox.warning(self, 'Return completed with issues', f'Returned {successes} submission(s).\nFailed: {", ".join(failures)}')
        else:
            QMessageBox.information(self, 'Returned', f'Returned {successes} submission(s).')

    def _return_one(self, subdir: Path) -> bool:
        manuscript_root = subdir.parent.parent
        events_dir = manuscript_root / 'events'
        reviews_dir = manuscript_root / 'reviews' / subdir.name
        reviews_dir.mkdir(parents=True, exist_ok=True)
        payload = subdir / 'payload'

        working_docx = reviews_dir / 'working.docx'
        working_doc = reviews_dir / 'working.doc'
        if working_docx.exists() or working_doc.exists():
            working = working_docx if working_docx.exists() else working_doc
            returned = reviews_dir / f'returned{working.suffix.lower()}'
            shutil.copy2(working, returned)
            if not (reviews_dir / 'comments.json').exists():
                save_comments_json(reviews_dir, {'general': 'Reviewed in Word', 'items': []})
            write_event(events_dir, returned_event(subdir.name))
            return True

        primary_word = None
        for ext in ('.docx', '.doc'):
            ps = sorted(payload.rglob(f'*{ext}'))
            if ps:
                primary_word = ps[0]; break
        if primary_word is not None:
            returned = reviews_dir / f'returned{primary_word.suffix.lower()}'
            shutil.copy2(primary_word, returned)
            if not (reviews_dir / 'comments.json').exists():
                save_comments_json(reviews_dir, {'general': 'Reviewed in Word (from submitted file)', 'items': []})
            write_event(events_dir, returned_event(subdir.name))
            return True

        worktree = reviews_dir / 'worktree' if (reviews_dir / 'worktree').exists() else payload
        diff_ok, diff_log, diff_pdf = build_diff_pdf(payload, worktree, reviews_dir)
        pdf_path = diff_pdf
        if not diff_ok or not (pdf_path and pdf_path.exists()):
            pdf_path = reviews_dir / 'compiled.pdf'
            if not pdf_path.exists():
                main_rel = detect_main_tex(worktree)
                if main_rel:
                    _ok, _log, _ = build_pdf(worktree, main_rel, pdf_path)

        comments = load_comments_json(reviews_dir)
        returned_html = reviews_dir / 'returned.html'
        title = manuscript_root.name
        try:
            manifest = json.loads((subdir / 'manifest.json').read_text(encoding='utf-8'))
            title = manifest.get('manuscript_title', title)
        except Exception:
            pass

        write_latex_review_html(
            returned_html,
            title=f'{title} (Returned)',
            has_pdf=bool(pdf_path and pdf_path.exists()),
            pdf_path=pdf_path if (pdf_path and pdf_path.exists()) else None,
            build_log=(diff_log if diff_ok else '(No latexdiff; plain build.)'),
            payload=payload,
            comments=comments,
        )
        if not (reviews_dir / 'comments.json').exists():
            save_comments_json(reviews_dir, {'general': '', 'items': []})

        write_event(events_dir, returned_event(subdir.name))
        return True

    # Window state + helpers
    def closeEvent(self, ev):
        if hasattr(self, '_settings'):
            self._settings.setValue('geometry', self.saveGeometry())
            self._settings.setValue('state', self.saveState())
        super().closeEvent(ev)

    def _clear_filters(self) -> None:
        self.ed_search.clear()
        self.cb_status.setCurrentIndex(0)
        self.cb_type.setCurrentIndex(0)
        self.scan_root()

    def _toggle_autorescan(self, checked: bool) -> None:
        if checked:
            self._timer.start()
            self.statusBar().showMessage('Auto-rescan: on (every 90s)', 3000)
        else:
            self._timer.stop()
            self.statusBar().showMessage('Auto-rescan: off', 3000)

    def _show_tree_menu(self, pos) -> None:
        item = self.tree.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        open_act = menu.addAction('Open')
        notes_act = menu.addAction('Review notes…')
        ret_act = menu.addAction('Return selected')
        update_act = menu.addAction('Check for updates…')
        act = menu.exec_(self.tree.viewport().mapToGlobal(pos))
        if act == open_act:
            if not item.data(0, Qt.UserRole) and item.childCount():
                self._open_path(Path(item.child(0).data(0, Qt.UserRole)))
            else:
                p = item.data(0, Qt.UserRole)
                if p:
                    self._open_path(Path(p))
        elif act == notes_act:
            item.setSelected(True)
            self._open_notes_dialog()
        elif act == ret_act:
            self._return_selected_batch()
        elif act == update_act:
            self._check_updates()


def main() -> None:
    app = QApplication(sys.argv)
    window = SupervisorWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
