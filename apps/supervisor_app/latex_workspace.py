from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QFont, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStyle,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from shared.latex.builder import build_pdf, detect_main_tex
from shared.latex.diff import build_diff_pdf  # ⬅️ new


# ------------------------- JSON helpers -------------------------
def load_comments_json(reviews_dir: Path) -> dict:
    f = reviews_dir / "comments.json"
    if f.exists():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("general", "")
                data.setdefault("items", [])
                return data
        except Exception:
            pass
    return {"general": "", "items": []}

def save_comments_json(reviews_dir: Path, data: dict) -> None:
    (reviews_dir / "comments.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

# ---------------------------- utils ----------------------------
def open_with_default_app(path: Path) -> None:
    if sys.platform.startswith("win"):
        import os
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)

def read_text_guess(path: Path) -> str:
    for enc in ("utf-8", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except Exception:
            pass
    return ""

def write_text_utf8(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

# --------------------------- dialog ----------------------------
class LatexWorkspace(QDialog):
    """
    Tối giản toolbar:
      - Save all & Close (Ctrl+S): lưu file → lưu comments → build compiled.pdf → build compiled_diff.pdf → đóng.
      - Build PDF (Ctrl+B): build compiled.pdf từ worktree (không đóng).
      - Preview diff PDF: mở compiled_diff.pdf (tạo nếu chưa có).
    """
    def __init__(self, parent: QWidget, submission_dir: Path, reviews_dir: Path) -> None:
        super().__init__(parent)
        self.setWindowTitle("LaTeX Review Workspace")
        self.resize(1200, 760)

        self.submission_dir = submission_dir
        self.reviews_dir = reviews_dir
        self.payload_dir = submission_dir / "payload"
        self.worktree_dir = reviews_dir / "worktree"
        self.compiled_pdf = reviews_dir / "compiled.pdf"
        self._last_built_pdf: Optional[Path] = None
        self.current_file: Optional[Path] = None
        self._dirty = False

        self._ensure_worktree()

        # ---------- toolbar ----------
        tb = QToolBar("Actions", self)
        tb.setIconSize(QSize(18, 18))
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

        def act(std_icon, text, slot, shortcut: Optional[QKeySequence] = None):
            a = QAction(self.style().standardIcon(std_icon), text, self)
            if shortcut:
                a.setShortcut(shortcut)
            a.triggered.connect(slot)
            tb.addAction(a)
            return a

        act(QStyle.SP_DialogSaveButton, "Save all and Close", self.save_all_and_close, QKeySequence("Ctrl+S"))
        tb.addSeparator()
        act(QStyle.SP_ArrowRight, "Build PDF", self.build_pdf_clicked, QKeySequence("Ctrl+B"))
        act(QStyle.SP_BrowserReload, "Preview diff PDF", self.preview_diff_pdf)

        # Shortcut “Add comment from selection” (không hiện trên toolbar)
        self._act_quick_comment = QAction("Add comment from selection", self)
        self._act_quick_comment.setShortcut(QKeySequence("Ctrl+Shift+C"))
        self._act_quick_comment.triggered.connect(self.add_comment_from_selection)
        self.addAction(self._act_quick_comment)

        # ---------- layout ----------
        outer = QVBoxLayout(self)
        outer.addWidget(tb)
        split_main = QSplitter(Qt.Horizontal, self)

        # Left panel
        left_box = QGroupBox("Files")
        left_layout = QVBoxLayout(left_box)
        self.ed_filter = QLineEdit(self)
        self.ed_filter.setPlaceholderText("Filter files (e.g. .tex, .bib, figures)")
        self.ed_filter.textChanged.connect(self._apply_filter)
        left_layout.addWidget(self.ed_filter)
        self.list_files = QListWidget(self)
        self.list_files.itemSelectionChanged.connect(self._on_file_selected)
        left_layout.addWidget(self.list_files, stretch=1)

        # Centre: editor + status + build log
        centre_box = QGroupBox("Editor")
        centre_layout = QVBoxLayout(centre_box)
        self.editor = QPlainTextEdit(self)
        mono = QFont("Menlo" if sys.platform == "darwin" else "Consolas"); mono.setStyleHint(QFont.Monospace); mono.setPointSize(12)
        self.editor.setFont(mono)
        self.editor.textChanged.connect(self._on_editor_changed)
        self.editor.cursorPositionChanged.connect(self._sync_comment_line_from_cursor)
        try:
            self.editor.selectionChanged.connect(self._sync_comment_line_from_cursor)  # type: ignore[attr-defined]
        except Exception:
            pass
        centre_layout.addWidget(self.editor, stretch=1)
        self.editor_status = QLabel("No file opened", self); self.editor_status.setStyleSheet("color:#666;")
        centre_layout.addWidget(self.editor_status)
        self.log_box = QPlainTextEdit(self); self.log_box.setReadOnly(True); self.log_box.setPlaceholderText("Build log will appear here…"); self.log_box.setMaximumHeight(160)
        centre_layout.addWidget(self.log_box)

        # Right: comments
        right_box = QGroupBox("Comments")
        right_layout = QVBoxLayout(right_box)
        right_layout.addWidget(QLabel("General notes:"))
        self.ed_general = QTextEdit(self); right_layout.addWidget(self.ed_general)

        right_layout.addWidget(QLabel("Itemised comments:"))
        grid = QGridLayout(); right_layout.addLayout(grid)
        grid.addWidget(QLabel("Line start:"), 0, 0); self.spin_start = QSpinBox(self); self.spin_start.setRange(1, 999999); grid.addWidget(self.spin_start, 0, 1)
        grid.addWidget(QLabel("Line end:"), 0, 2); self.spin_end = QSpinBox(self); self.spin_end.setRange(1, 999999); grid.addWidget(self.spin_end, 0, 3)
        grid.addWidget(QLabel("Text:"), 1, 0); self.ed_item_text = QLineEdit(self); grid.addWidget(self.ed_item_text, 1, 1, 1, 3)

        btn_row = QHBoxLayout()
        self.btn_add = QPushButton("Add"); self.btn_del = QPushButton("Delete selected")
        self.btn_add.clicked.connect(self.add_comment_from_fields); self.btn_del.clicked.connect(self.delete_selected_comment)
        btn_row.addStretch(1); btn_row.addWidget(self.btn_add); btn_row.addWidget(self.btn_del)
        right_layout.addLayout(btn_row)

        self.list_comments = QListWidget(self); right_layout.addWidget(self.list_comments, stretch=1)

        split_main.addWidget(left_box); split_main.addWidget(centre_box); split_main.addWidget(right_box)
        split_main.setSizes([260, 680, 360])
        outer.addWidget(split_main, stretch=1)

        self.setStyleSheet("""
            QListWidget { font-size: 13px; }
            QPlainTextEdit { font-family: Menlo, Consolas, monospace; }
            QPushButton { padding: 6px 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
        """)

        self._refresh_file_list()
        self._load_comments()
        self._sync_comment_line_from_cursor()

    # --------- worktree ----------
    def _ensure_worktree(self) -> None:
        if self.worktree_dir.exists():
            return
        for p in self.payload_dir.rglob("*"):
            if p.is_dir(): continue
            rel = p.relative_to(self.payload_dir)
            dst = self.worktree_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dst)

    # --------- files & filter ----------
    def _refresh_file_list(self) -> None:
        self.list_files.clear()
        files = [p for p in self.worktree_dir.rglob("*") if p.is_file()]
        files_tex = [p for p in files if p.suffix.lower() == ".tex"]
        files_oth = [p for p in files if p.suffix.lower() != ".tex"]

        def add_item(p: Path):
            it = QListWidgetItem(str(p.relative_to(self.worktree_dir)), self.list_files)
            it.setData(Qt.UserRole, str(p))
        for p in files_tex + files_oth:
            add_item(p)
        self._apply_filter()

        main_rel = detect_main_tex(self.worktree_dir)
        if main_rel:
            target = str(main_rel).replace("\\", "/")
            for i in range(self.list_files.count()):
                it = self.list_files.item(i)
                if it.text().replace("\\", "/") == target:
                    self.list_files.setCurrentItem(it)
                    break

    def _apply_filter(self) -> None:
        q = (self.ed_filter.text() or "").strip().lower()
        for i in range(self.list_files.count()):
            it = self.list_files.item(i)
            it.setHidden(q not in it.text().lower())

    # --------- editor ----------
    def _on_file_selected(self) -> None:
        items = self.list_files.selectedItems()
        if not items:
            self.current_file = None
            self.editor.clear()
            self.editor_status.setText("No file opened")
            self.spin_start.setValue(1); self.spin_end.setValue(1)
            return
        if self._dirty and self.current_file:
            if QMessageBox.question(self, "Unsaved changes", "Save current file before switching?",
                                    QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                self.save_current_file()

        path = Path(items[0].data(Qt.UserRole))
        self.current_file = path
        self.editor.setPlainText(read_text_guess(path))
        self._dirty = False
        self._update_editor_status()
        self._sync_comment_line_from_cursor()

    def _on_editor_changed(self) -> None:
        if self.current_file is None: return
        self._dirty = True; self._update_editor_status()

    def _update_editor_status(self) -> None:
        c = self.editor.textCursor()
        line, col = c.blockNumber() + 1, c.columnNumber() + 1
        name = self.current_file.relative_to(self.worktree_dir) if self.current_file else "(none)"
        self.editor_status.setText(f"{name} — Ln {line}, Col {col}{' • modified' if self._dirty else ''}")

    def save_current_file(self) -> None:
        if not self.current_file: return
        try:
            write_text_utf8(self.current_file, self.editor.toPlainText())
            self._dirty = False; self._update_editor_status()
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))

    # --------- build / open ----------
    def build_pdf_clicked(self) -> None:
        if self._dirty: self.save_current_file()
        main_rel = detect_main_tex(self.worktree_dir) or detect_main_tex(self.payload_dir)
        root = self.worktree_dir if detect_main_tex(self.worktree_dir) else self.payload_dir
        if main_rel is None:
            QMessageBox.warning(self, "No .tex", "Cannot find a main .tex file to build.")
            return
        self.log_box.setPlainText("Building…")
        ok, log, produced = build_pdf(root, main_rel, self.compiled_pdf)
        self.log_box.setPlainText(log or "(no log)")
        if ok:
            try:
                if produced and produced.exists() and produced.resolve() != self.compiled_pdf.resolve():
                    shutil.copy2(produced, self.compiled_pdf)
                self._last_built_pdf = self.compiled_pdf if self.compiled_pdf.exists() else produced
            except Exception:
                self._last_built_pdf = produced
            QMessageBox.information(self, "Build", "PDF compiled successfully.")
        else:
            QMessageBox.warning(self, "Build", "Build failed. See log for details.")

    def preview_diff_pdf(self) -> None:
        if self._dirty: self.save_current_file()
        self.log_box.setPlainText("Building diff…")
        ok, log, produced = build_diff_pdf(self.payload_dir, self.worktree_dir, self.reviews_dir)
        self.log_box.setPlainText(log or "(no log)")
        if ok and produced and produced.exists():
            open_with_default_app(produced)
        else:
            QMessageBox.warning(self, "Diff", "Could not build diff. See log for details.")

    # --------- comments ----------
    def _load_comments(self) -> None:
        self._comments = load_comments_json(self.reviews_dir)
        self.ed_general.setPlainText(self._comments.get("general", ""))
        self._refresh_comments_view()

    def _refresh_comments_view(self) -> None:
        self.list_comments.clear()
        for it in self._comments.get("items", []):
            f = it.get("file", "")
            ls = it.get("line_start", it.get("line", ""))
            le = it.get("line_end", ls)
            t = it.get("text", "")
            loc = f"{f}:{ls}" if ls == le else f"{f} [{ls}-{le}]"
            QListWidgetItem(f"{loc} — {t}", self.list_comments)

    def add_comment_from_fields(self) -> None:
        file_rel = self._current_rel_path()
        if not file_rel:
            QMessageBox.information(self, "No file", "Open a file to attach the comment to.")
            return
        txt = self.ed_item_text.text().strip()
        if not txt: return
        s = int(self.spin_start.value()); e = max(s, int(self.spin_end.value()))
        self._comments.setdefault("items", []).append({"file": file_rel, "line_start": s, "line_end": e, "text": txt})
        self.ed_item_text.clear(); self._refresh_comments_view()

    def add_comment_from_selection(self) -> None:
        file_rel = self._current_rel_path()
        if not file_rel:
            QMessageBox.information(self, "No file", "Open a file to attach the comment to.")
            return
        cursor = self.editor.textCursor()
        if not cursor.hasSelection():
            s = e = cursor.blockNumber() + 1
        else:
            s = self._pos_to_line(min(cursor.selectionStart(), cursor.selectionEnd()))
            e = self._pos_to_line(max(cursor.selectionStart(), cursor.selectionEnd()))
        self.spin_start.setValue(s); self.spin_end.setValue(e)
        txt = self.ed_item_text.text().strip() or "Add new line"
        self._comments.setdefault("items", []).append({"file": file_rel, "line_start": int(s), "line_end": int(e), "text": txt})
        self.ed_item_text.clear(); self._refresh_comments_view()

    def delete_selected_comment(self) -> None:
        row = self.list_comments.currentRow()
        if row < 0: return
        try: del self._comments["items"][row]
        except Exception: pass
        self._refresh_comments_view()

    def _current_rel_path(self) -> Optional[str]:
        if not self.current_file: return None
        try: rel = self.current_file.relative_to(self.worktree_dir)
        except Exception: return None
        return str(rel).replace("\\", "/")

    def _pos_to_line(self, pos: int) -> int:
        doc = self.editor.document(); block = doc.findBlock(pos)
        return block.blockNumber() + 1

    def _sync_comment_line_from_cursor(self) -> None:
        try:
            c = self.editor.textCursor()
            if not c: return
            if c.hasSelection():
                s_line = self._pos_to_line(min(c.selectionStart(), c.selectionEnd()))
                e_line = self._pos_to_line(max(c.selectionStart(), c.selectionEnd()))
            else:
                s_line = e_line = c.blockNumber() + 1
            self.spin_start.blockSignals(True); self.spin_end.blockSignals(True)
            self.spin_start.setValue(max(1, int(s_line))); self.spin_end.setValue(max(1, int(e_line)))
            self.spin_start.blockSignals(False); self.spin_end.blockSignals(False)
        except Exception:
            pass

    # --------- Save-all & lifecycle ----------
    def save_all_and_close(self) -> None:
        # 1) save current file (if modified)
        if self._dirty: self.save_current_file()
        # 2) save comments
        self._comments["general"] = self.ed_general.toPlainText()
        try:
            save_comments_json(self.reviews_dir, self._comments)
        except Exception as e:
            QMessageBox.critical(self, "Save comments failed", str(e))
            # vẫn tiếp tục các bước sau để không mất tiến độ

        # 3) build compiled.pdf
        main_rel = detect_main_tex(self.worktree_dir) or detect_main_tex(self.payload_dir)
        root = self.worktree_dir if detect_main_tex(self.worktree_dir) else self.payload_dir
        ok1, log1, _ = (False, "(no main .tex)", None)
        if main_rel:
            ok1, log1, _ = build_pdf(root, main_rel, self.compiled_pdf)

        # 4) build diff PDF
        ok2, log2, produced = build_diff_pdf(self.payload_dir, self.worktree_dir, self.reviews_dir)

        # 5) report + close
        msg = []
        msg.append("Saved file(s) and comments.")
        msg.append(f"Build compiled.pdf: {'OK' if ok1 else 'FAILED'}")
        msg.append(f"Build diff: {'OK' if ok2 else 'FAILED'}")
        self.log_box.setPlainText(((log1 or "") + "\n" + (log2 or "")).strip())
        QMessageBox.information(self, "Saved", "\n".join(msg))
        self.accept()

    def closeEvent(self, ev):
        if self._dirty:
            ans = QMessageBox.question(self, "Unsaved changes", "Save current file before closing?",
                                       QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            if ans == QMessageBox.Yes:
                self.save_current_file()
            elif ans == QMessageBox.Cancel:
                ev.ignore(); return
        super().closeEvent(ev)

# Manual debug
if __name__ == "__main__":
    app = QApplication(sys.argv)
    sub = Path.cwd(); rev = Path.cwd()
    dlg = LatexWorkspace(None, submission_dir=sub, reviews_dir=rev)
    dlg.exec()
