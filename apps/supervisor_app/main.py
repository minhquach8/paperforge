from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

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

from apps.supervisor_app.data import SubmissionInfo
from apps.supervisor_app.dialogs import prompt_due_datetime
from apps.supervisor_app.scan import mtype_label, scan_students_root
from apps.supervisor_app.services import (
    clear_due_many,
    open_submission,
    return_submission,
    set_due_many,
    tooltip_for,
)
from shared.buildinfo import get_display_version, get_repo
from shared.config import load_config, save_config
from shared.timeutil import iso_to_local_str
from shared.ui.update_qt import check_for_updates
from shared.updater import cleanup_legacy_appdata_if_any

APP_NAME = "Paperforge — Supervisor"
RECENTS_KEY = "supervisor_recent_roots"
MAX_RECENTS = 5

STATUS_COLOURS = {
    "New": ("#E8F0FE", "#0B57D0"),
    "In review": ("#FFF8E1", "#8C6D1F"),
    "Returned": ("#E6F4EA", "#0F6D31"),
}

class SupervisorWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1300, 860)

        central = QWidget(self); root = QVBoxLayout(central)

        # Toolbar
        tb = QToolBar("Quick actions", self)
        tb.setIconSize(QSize(18, 18))
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(tb)
        def _act(icon, text, slot, checkable=False):
            a = QAction(self.style().standardIcon(icon), text, self)
            a.setCheckable(checkable); a.triggered.connect(slot); tb.addAction(a); return a
        _act(QStyle.SP_DirOpenIcon, "Choose Students’ Root…", self.choose_root)
        _act(QStyle.SP_BrowserReload, "Scan", self.scan_root)
        tb.addSeparator()
        _act(QStyle.SP_ArrowDown, "Expand all", lambda: self.tree.expandAll())
        _act(QStyle.SP_ArrowUp, "Collapse all", lambda: self.tree.collapseAll())
        tb.addSeparator()
        _act(QStyle.SP_DialogResetButton, "Clear filters", self._clear_filters)
        tb.addSeparator()
        self.act_autorescan = _act(QStyle.SP_BrowserReload, "Auto-rescan", self._toggle_autorescan, checkable=True)
        tb.addSeparator()
        _act(QStyle.SP_BrowserReload, "Check for updates…", self._check_updates)

        # Labels + recents
        self.lbl_root = QLabel("Students’ Root: (none)", self); self.lbl_root.setStyleSheet("color:#444;")
        self.lbl_root.setTextInteractionFlags(Qt.TextSelectableByMouse); root.addWidget(self.lbl_root)
        row = QHBoxLayout(); row.addWidget(QLabel("Recent:"))
        self.cb_recent = QComboBox(self); self.btn_use_recent = QPushButton("Open"); self.btn_clear_recent = QPushButton("Clear")
        self.btn_use_recent.clicked.connect(self._use_selected_recent); self.btn_clear_recent.clicked.connect(self._clear_recents)
        self.cb_recent.activated.connect(lambda _ix: self._use_selected_recent())
        row.addWidget(self.cb_recent, 1); row.addWidget(self.btn_use_recent); row.addWidget(self.btn_clear_recent); root.addLayout(row)

        # Filters
        filters = QHBoxLayout()
        filters.addWidget(QLabel("Search:"))
        self.ed_search = QLineEdit(self); self.ed_search.setPlaceholderText("Student / Manuscript / Journal / Submission ID")
        self.ed_search.setClearButtonEnabled(True); self.ed_search.textChanged.connect(self.scan_root)
        filters.addWidget(self.ed_search, 1)
        filters.addWidget(QLabel("Status:")); self.cb_status = QComboBox(self); self.cb_status.addItems(["All","New","In review","Returned"]); self.cb_status.currentIndexChanged.connect(self.scan_root); filters.addWidget(self.cb_status)
        filters.addWidget(QLabel("Type:")); self.cb_type = QComboBox(self); self.cb_type.addItems(["All","Word","LaTeX"]); self.cb_type.currentIndexChanged.connect(self.scan_root); filters.addWidget(self.cb_type)
        root.addLayout(filters)

        # Legend
        legend = QLabel(
            "Legend: "
            '<span style="background:#E8F0FE;border:1px solid #9EB7F6;padding:2px 8px;border-radius:6px;">New</span> '
            '<span style="background:#FFF8E1;border:1px solid #E7D390;padding:2px 8px;border-radius:6px;">In review</span> '
            '<span style="background:#E6F4EA;border:1px solid #9CD3B0;padding:2px 8px;border-radius:6px;">Returned</span> '
            '<span style="background:#FDE7E9;border:1px solid #F3A6AE;color:#B00020;padding:2px 8px;border-radius:6px;">Overdue</span>')
        legend.setStyleSheet("color:#444;"); root.addWidget(legend)

        # Tree
        self.tree = QTreeWidget(self)
        self.tree.setColumnCount(9)
        self.tree.setHeaderLabels(["Student","Manuscript","Journal","Submission","Type","Status","When","Due","Last Edit"])
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.setUniformRowHeights(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSortingEnabled(True); self.tree.sortByColumn(0, Qt.AscendingOrder)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu); self.tree.customContextMenuRequested.connect(self._show_tree_menu)
        self.tree.itemDoubleClicked.connect(self._open_item)
        root.addWidget(self.tree, 1)

        # Action buttons
        actions = QHBoxLayout()
        self.btn_open = QPushButton("Open"); self.btn_notes = QPushButton("Review notes…"); self.btn_return = QPushButton("Return selected")
        self.btn_open.clicked.connect(self._open_selected); self.btn_notes.clicked.connect(self._open_notes_dialog); self.btn_return.clicked.connect(self._return_selected_batch)
        actions.addWidget(self.btn_open); actions.addWidget(self.btn_notes); actions.addWidget(self.btn_return); root.addLayout(actions)

        # Footer
        credit = QLabel("Made by Minh Quach", self); credit.setStyleSheet("color:#666; padding-left:12px;")
        self.statusBar().addPermanentWidget(credit)
        self.lbl_ver = QLabel(f"v{get_display_version()}", self); self.lbl_ver.setStyleSheet("color:#666; padding-left:12px;")
        self.statusBar().addPermanentWidget(self.lbl_ver)

        self.students_root: Optional[Path] = None
        self._settings = QSettings("Paperforge", "Supervisor")
        if self._settings.value("geometry"): self.restoreGeometry(self._settings.value("geometry"))
        if self._settings.value("state"): self.restoreState(self._settings.value("state"))

        self._timer = QTimer(self); self._timer.setInterval(90_000); self._timer.timeout.connect(self.scan_root)

        self.setCentralWidget(central)
        self.statusBar().showMessage("Ready", 3000)
        cleanup_legacy_appdata_if_any()
        self._update_recent_ui()
        recents = self._load_recent_roots()
        if recents and Path(recents[0]).exists():
            self._set_students_root(Path(recents[0]), remember=False, autoscan=True)

    # ── Recents / root
    def _update_root_label(self) -> None:
        self.lbl_root.setText(f"Students’ Root: {str(self.students_root) if self.students_root else '(none)'}")

    def _set_students_root(self, path: Path, *, remember=True, autoscan=True) -> None:
        self.students_root = path; self._update_root_label()
        if remember: self._remember_root(path)
        if autoscan: self.scan_root()

    def _load_recent_roots(self) -> list[str]:
        cfg = load_config(); roots = cfg.get(RECENTS_KEY, []); 
        if not isinstance(roots, list): roots = []
        out, seen = [], set()
        for r in roots:
            if isinstance(r, str) and r not in seen and Path(r).exists():
                out.append(r); seen.add(r)
        return out

    def _save_recent_roots(self, roots: list[str]) -> None:
        cfg = load_config(); cfg[RECENTS_KEY] = roots[:MAX_RECENTS]; save_config(cfg)

    def _remember_root(self, path: Path) -> None:
        s = str(path); roots = [r for r in self._load_recent_roots() if r != s]; roots.insert(0, s)
        self._save_recent_roots(roots); self._update_recent_ui()

    def _update_recent_ui(self) -> None:
        roots = self._load_recent_roots()
        self.cb_recent.blockSignals(True); self.cb_recent.clear()
        for r in roots: self.cb_recent.addItem(r)
        self.cb_recent.blockSignals(False)
        enabled = bool(roots); self.btn_use_recent.setEnabled(enabled); self.btn_clear_recent.setEnabled(enabled)

    def _use_selected_recent(self) -> None:
        text = (self.cb_recent.currentText() or "").strip()
        if not text: return
        p = Path(text)
        if not p.exists():
            QMessageBox.warning(self, "Not found", f"Folder no longer exists:\n{text}")
            roots = [r for r in self._load_recent_roots() if r != text]; self._save_recent_roots(roots); self._update_recent_ui(); return
        self._set_students_root(p, remember=True, autoscan=True)

    def _clear_recents(self) -> None:
        self._save_recent_roots([]); self._update_recent_ui()

    # ── Updates
    def _check_updates(self) -> None:
        check_for_updates(self, app_id="supervisor", repo=get_repo(), current_version=get_display_version(), app_keyword="Supervisor")

    # ── Toolbar helpers
    def _clear_filters(self) -> None:
        self.ed_search.clear(); self.cb_status.setCurrentIndex(0); self.cb_type.setCurrentIndex(0); self.scan_root()

    def _toggle_autorescan(self, checked: bool) -> None:
        (self._timer.start() if checked else self._timer.stop())
        self.statusBar().showMessage(f"Auto-rescan: {'on (every 90s)' if checked else 'off'}", 3000)

    # ── Scan + paint
    def _apply_status_style(self, item: QTreeWidgetItem, status: str) -> None:
        colours = STATUS_COLOURS.get(status); 
        if not colours: return
        bg_hex, fg_hex = colours; bg = QBrush(QColor(bg_hex)); fg = QBrush(QColor(fg_hex))
        for col in range(self.tree.columnCount()):
            item.setBackground(col, bg); item.setForeground(col, fg)
        f = QFont(self.font()); f.setBold(True); item.setFont(5, f)

    def scan_root(self) -> None:
        self.tree.clear()
        if not self.students_root: return

        infos = scan_students_root(
            self.students_root,
            text_query=self.ed_search.text(),
            status_filter=self.cb_status.currentText(),
            type_filter=self.cb_type.currentText(),
        )

        # group by student
        by_student: dict[str, list[SubmissionInfo]] = {}
        for info in infos: by_student.setdefault(info.student, []).append(info)

        total = 0
        for student, rows in sorted(by_student.items()):
            parent = QTreeWidgetItem([f"{student}   ({len(rows)})"] + [""] * 8)
            parent.setFirstColumnSpanned(True); self.tree.addTopLevelItem(parent); parent.setExpanded(True)
            for info in rows:
                due_label = ""
                if info.due_iso:
                    try: due_label = iso_to_local_str(info.due_iso)
                    except Exception: due_label = info.due_iso
                    if info.overdue: due_label = f"{due_label}  ⚠ OVERDUE"

                it = QTreeWidgetItem([
                    info.student,
                    info.manuscript_title,
                    info.journal,
                    info.submission_id,
                    mtype_label(info.mtype),
                    info.status,
                    info.when_label,
                    due_label,
                    iso_to_local_str(info.last_edit_iso),
                ])
                self._apply_status_style(it, info.status)
                if info.overdue:
                    it.setForeground(7, QBrush(QColor("#B00020"))); f = QFont(self.font()); f.setBold(True); it.setFont(7, f)
                # stash SubmissionInfo
                it.setData(0, Qt.UserRole, info)  # store the whole object
                tip = tooltip_for(info)
                if tip:
                    for col in range(self.tree.columnCount()):
                        it.setToolTip(col, tip)
                parent.addChild(it); total += 1

        for col in (0,1,2,4,5,7,8):
            self.tree.resizeColumnToContents(col)
        self.statusBar().showMessage(f"Found {total} submission(s) after filters.", 5000)

    # ── Selection helpers
    def _selected_infos(self) -> list[SubmissionInfo]:
        out: list[SubmissionInfo] = []
        for it in self.tree.selectedItems():
            data = it.data(0, Qt.UserRole)
            if isinstance(data, SubmissionInfo):
                out.append(data)
        return out

    # ── Actions
    def _open_item(self, item: QTreeWidgetItem, _col: int) -> None:
        data = item.data(0, Qt.UserRole)
        if isinstance(data, SubmissionInfo):
            open_submission(self, data)
        elif item.childCount():
            ch = item.child(0).data(0, Qt.UserRole)
            if isinstance(ch, SubmissionInfo): open_submission(self, ch)

    def _open_selected(self) -> None:
        infos = self._selected_infos()
        if infos: open_submission(self, infos[0])

    def _open_notes_dialog(self) -> None:
        # Word notes dialog đã được quản trị ở LatexWorkspace hoặc Word review;
        # Ở bản refactor này ta mở submission; người dùng chỉnh trong workspace/Word.
        self._open_selected()

    def _return_selected_batch(self) -> None:
        infos = self._selected_infos()
        if not infos:
            QMessageBox.information(self, "Return", "Please select one or more submissions."); return
        ok, fail = 0, []
        for info in infos:
            try:
                if return_submission(info): ok += 1
                else: fail.append(info.submission_id)
            except Exception as e:
                fail.append(f"{info.submission_id} ({e})")
        self.scan_root()
        if fail:
            QMessageBox.warning(self, "Return – partial", f"Returned {ok} submission(s).\nFailed: {', '.join(fail)}")
        else:
            QMessageBox.information(self, "Returned", f"Returned {ok} submission(s).")

    # ── Menu
    def _show_tree_menu(self, pos) -> None:
        item = self.tree.itemAt(pos)
        if not item: return
        menu = QMenu(self)
        open_act = menu.addAction("Open")
        ret_act = menu.addAction("Return selected")
        update_act = menu.addAction("Check for updates…")
        due_set_act = menu.addAction("Set expected return date…")
        due_clear_act = menu.addAction("Clear expected return date")

        info = item.data(0, Qt.UserRole)
        view_due_note_act = None
        if isinstance(info, SubmissionInfo) and (info.due_note or "").strip():
            view_due_note_act = menu.addAction("View due note…")

        act = menu.exec_(self.tree.viewport().mapToGlobal(pos))
        if act == open_act:
            self._open_item(item, 0)
        elif act == ret_act:
            self._return_selected_batch()
        elif act == update_act:
            self._check_updates()
        elif act == due_set_act:
            infos = self._selected_infos()
            if not infos: return
            iso, note = prompt_due_datetime(self)
            if iso:
                try:
                    set_due_many(infos, iso, note, set_by="supervisor")
                    self.scan_root(); self.statusBar().showMessage("Due date updated.", 3000)
                except Exception as e:
                    QMessageBox.warning(self, "Set due failed", str(e))
        elif act == due_clear_act:
            infos = self._selected_infos()
            if infos:
                try:
                    clear_due_many(infos); self.scan_root(); self.statusBar().showMessage("Due date cleared.", 3000)
                except Exception as e:
                    QMessageBox.warning(self, "Clear due failed", str(e))
        elif view_due_note_act and act == view_due_note_act and isinstance(info, SubmissionInfo):
            QMessageBox.information(self, "Due note", info.due_note)

    # ── Window state
    def closeEvent(self, ev):
        if hasattr(self, "_settings"):
            self._settings.setValue("geometry", self.saveGeometry())
            self._settings.setValue("state", self.saveState())
        super().closeEvent(ev)

    # ── Root picker
    def choose_root(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Students’ Root (OneDrive)")
        if folder: self._set_students_root(Path(folder), remember=True, autoscan=True)

def main() -> None:
    app = QApplication(sys.argv)
    w = SupervisorWindow(); w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
