# apps/supervisor_app/latex_workspace.py
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

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


# ─────────────────────────────────────────────────────────────────────────────
# Comments json helpers (kept public for Supervisor main imports)
# ─────────────────────────────────────────────────────────────────────────────
def load_comments_json(reviews_dir: Path) -> dict:
    """
    Schema:
      {
        "general": "free text",
        "items": [{"file": "path/rel", "line": 12 OR "line_start": 1, "line_end": 3, "text": "comment"}]
      }
    """
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


# ─────────────────────────────────────────────────────────────────────────────
# Small utilities
# ─────────────────────────────────────────────────────────────────────────────
def open_with_default_app(path: Path) -> None:
    """Open with system default app (Preview/Acrobat on macOS/Windows)."""
    if sys.platform.startswith("win"):
        import os
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


def read_text_guess(path: Path) -> str:
    """Best-effort read with utf-8 → latin-1 fallback (no crash)."""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        try:
            return path.read_text(encoding="latin-1")
        except Exception:
            return ""


def write_text_utf8(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# Dialogue
# ─────────────────────────────────────────────────────────────────────────────
class LatexWorkspace(QDialog):
    """
    LaTeX review workspace (modal):
      - Creates/uses reviews/<id>/worktree as an isolated edit area (first run copies payload/ → worktree/).
      - File list (left) + editor (centre) + comments (right).
      - Build PDF into reviews/<id>/compiled.pdf.
      - Comments saved to reviews/<id>/comments.json.
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
        self.current_file: Optional[Path] = None
        self._dirty = False

        # One-off initialisation of worktree
        self._ensure_worktree()

        # ── Toolbar ────────────────────────────────────────────────────────
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

        act(QStyle.SP_DialogSaveButton, "Save file", self.save_current_file, QKeySequence("Ctrl+S"))
        tb.addSeparator()
        act(QStyle.SP_ArrowRight, "Build PDF", self.build_pdf_clicked, QKeySequence("Ctrl+B"))
        act(QStyle.SP_DialogOpenButton, "Open compiled.pdf", self.open_compiled_pdf)
        tb.addSeparator()
        act(QStyle.SP_FileDialogDetailedView, "Add comment from selection", self.add_comment_from_selection, QKeySequence("Ctrl+Shift+C"))
        act(QStyle.SP_DialogApplyButton, "Save comments", self.save_comments)

        # ── Layout ─────────────────────────────────────────────────────────
        outer = QVBoxLayout(self)
        outer.addWidget(tb)

        split_main = QSplitter(Qt.Horizontal, self)

        # Left panel: files + filter
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
        mono = QFont("Menlo" if sys.platform == "darwin" else "Consolas")
        mono.setStyleHint(QFont.Monospace)
        mono.setPointSize(12)
        self.editor.setFont(mono)
        self.editor.textChanged.connect(self._on_editor_changed)
        centre_layout.addWidget(self.editor, stretch=1)

        self.editor_status = QLabel("No file opened", self)
        self.editor_status.setStyleSheet("color:#666;")
        centre_layout.addWidget(self.editor_status)

        self.log_box = QPlainTextEdit(self)
        self.log_box.setReadOnly(True)
        self.log_box.setPlaceholderText("Build log will appear here…")
        self.log_box.setMaximumHeight(160)
        centre_layout.addWidget(self.log_box)

        # Right: comments
        right_box = QGroupBox("Comments")
        right_layout = QVBoxLayout(right_box)

        # General notes
        right_layout.addWidget(QLabel("General notes:"))
        self.ed_general = QTextEdit(self)
        right_layout.addWidget(self.ed_general)

        # Itemised comments editor
        right_layout.addWidget(QLabel("Itemised comments:"))
        grid = QGridLayout()
        right_layout.addLayout(grid)

        grid.addWidget(QLabel("Line start:"), 0, 0)
        self.spin_start = QSpinBox(self); self.spin_start.setMinimum(1); self.spin_start.setMaximum(999999)
        grid.addWidget(self.spin_start, 0, 1)

        grid.addWidget(QLabel("Line end:"), 0, 2)
        self.spin_end = QSpinBox(self); self.spin_end.setMinimum(1); self.spin_end.setMaximum(999999)
        grid.addWidget(self.spin_end, 0, 3)

        grid.addWidget(QLabel("Text:"), 1, 0)
        self.ed_item_text = QLineEdit(self)
        grid.addWidget(self.ed_item_text, 1, 1, 1, 3)

        btn_row = QHBoxLayout()
        self.btn_add = QPushButton("Add")
        self.btn_del = QPushButton("Delete selected")
        self.btn_add.clicked.connect(self.add_comment_from_fields)
        self.btn_del.clicked.connect(self.delete_selected_comment)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_add)
        btn_row.addWidget(self.btn_del)
        right_layout.addLayout(btn_row)

        self.list_comments = QListWidget(self)
        right_layout.addWidget(self.list_comments, stretch=1)

        # Put panels into splitter
        split_main.addWidget(left_box)
        split_main.addWidget(centre_box)
        split_main.addWidget(right_box)
        split_main.setSizes([260, 680, 360])
        outer.addWidget(split_main, stretch=1)

        # Style touch
        self.setStyleSheet("""
            QListWidget { font-size: 13px; }
            QPlainTextEdit { font-family: Menlo, Consolas, monospace; }
            QPushButton { padding: 6px 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
        """)

        # Load initial files + comments
        self._refresh_file_list()
        self._load_comments()

    # ──────────────────────────────────────────────────────────────────
    # Worktree initialisation
    # ──────────────────────────────────────────────────────────────────
    def _ensure_worktree(self) -> None:
        """
        Create worktree from payload once; on subsequent opens we preserve edits.
        """
        if self.worktree_dir.exists():
            return
        # Copy payload → worktree (files only)
        for p in self.payload_dir.rglob("*"):
            if p.is_dir():
                continue
            rel = p.relative_to(self.payload_dir)
            dst = self.worktree_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dst)

    # ──────────────────────────────────────────────────────────────────
    # File list & filtering
    # ──────────────────────────────────────────────────────────────────
    def _refresh_file_list(self) -> None:
        self.list_files.clear()
        files = [p for p in self.worktree_dir.rglob("*") if p.is_file()]
        # Prefer .tex on top, then others
        files_tex = [p for p in files if p.suffix.lower() == ".tex"]
        files_oth = [p for p in files if p.suffix.lower() != ".tex"]
        def add_item(p: Path):
            rel = p.relative_to(self.worktree_dir)
            it = QListWidgetItem(str(rel), self.list_files)
            it.setData(Qt.UserRole, str(p))
        for p in files_tex + files_oth:
            add_item(p)
        self._apply_filter()  # respect current filter

        # Auto-select main .tex if available
        main_rel = detect_main_tex(self.worktree_dir)
        if main_rel:
            for i in range(self.list_files.count()):
                it = self.list_files.item(i)
                if it.text().replace("\\", "/") == str(main_rel).replace("\\", "/"):
                    self.list_files.setCurrentItem(it)
                    break

    def _apply_filter(self) -> None:
        q = (self.ed_filter.text() or "").strip().lower()
        for i in range(self.list_files.count()):
            it = self.list_files.item(i)
            it.setHidden(q not in it.text().lower())

    # ──────────────────────────────────────────────────────────────────
    # Editor handling
    # ──────────────────────────────────────────────────────────────────
    def _on_file_selected(self) -> None:
        items = self.list_files.selectedItems()
        if not items:
            self.current_file = None
            self.editor.clear()
            self.editor_status.setText("No file opened")
            return

        # Offer to save if dirty
        if self._dirty and self.current_file:
            if QMessageBox.question(
                self, "Unsaved changes", "Save current file before switching?",
                QMessageBox.Yes | QMessageBox.No
            ) == QMessageBox.Yes:
                self.save_current_file()

        path = Path(items[0].data(Qt.UserRole))
        self.current_file = path
        self.editor.setPlainText(read_text_guess(path))
        self._dirty = False
        self._update_editor_status()

    def _on_editor_changed(self) -> None:
        if self.current_file is None:
            return
        self._dirty = True
        self._update_editor_status()

    def _update_editor_status(self) -> None:
        cursor = self.editor.textCursor()
        line = cursor.blockNumber() + 1
        col = cursor.columnNumber() + 1
        name = self.current_file.relative_to(self.worktree_dir) if self.current_file else "(none)"
        dirty = " • modified" if self._dirty else ""
        self.editor_status.setText(f"{name} — Ln {line}, Col {col}{dirty}")

    def save_current_file(self) -> None:
        if not self.current_file:
            return
        try:
            write_text_utf8(self.current_file, self.editor.toPlainText())
            self._dirty = False
            self._update_editor_status()
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))

    # ──────────────────────────────────────────────────────────────────
    # Build / open PDF
    # ──────────────────────────────────────────────────────────────────
    def build_pdf_clicked(self) -> None:
        # Always save current file first
        if self._dirty:
            self.save_current_file()

        # Choose main from worktree if possible; else fallback to payload
        main_rel = detect_main_tex(self.worktree_dir)
        root = self.worktree_dir
        if main_rel is None:
            main_rel = detect_main_tex(self.payload_dir)
            root = self.payload_dir

        if main_rel is None:
            QMessageBox.warning(self, "No .tex", "Cannot find a main .tex file to build.")
            return

        self.log_box.setPlainText("Building…")
        ok, log, produced = build_pdf(root, main_rel, self.compiled_pdf)
        self.log_box.setPlainText(log or "(no log)")

        if ok and self.compiled_pdf.exists():
            QMessageBox.information(self, "Build", "PDF compiled successfully.")
        else:
            QMessageBox.warning(self, "Build", "Build failed. See log for details.")

    def open_compiled_pdf(self) -> None:
        if not self.compiled_pdf.exists():
            QMessageBox.information(self, "Open PDF", "No compiled.pdf yet. Please build first.")
            return
        open_with_default_app(self.compiled_pdf)

    # ──────────────────────────────────────────────────────────────────
    # Comments handling
    # ──────────────────────────────────────────────────────────────────
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
            if ls == le:
                loc = f"{f}:{ls}"
            else:
                loc = f"{f} [{ls}-{le}]"
            QListWidgetItem(f"{loc} — {t}", self.list_comments)

    def add_comment_from_fields(self) -> None:
        file_rel = self._current_rel_path()
        if not file_rel:
            QMessageBox.information(self, "No file", "Open a file to attach the comment to.")
            return
        txt = self.ed_item_text.text().strip()
        if not txt:
            return
        s = int(self.spin_start.value())
        e = int(self.spin_end.value())
        if e < s:
            e = s
            self.spin_end.setValue(e)
        self._comments.setdefault("items", []).append(
            {"file": file_rel, "line_start": s, "line_end": e, "text": txt}
        )
        self.ed_item_text.clear()
        self._refresh_comments_view()

    def add_comment_from_selection(self) -> None:
        """Compute line range from current selection and add quickly."""
        file_rel = self._current_rel_path()
        if not file_rel:
            QMessageBox.information(self, "No file", "Open a file to attach the comment to.")
            return
        cursor = self.editor.textCursor()
        if not cursor.hasSelection():
            # If no selection, take current line
            s = e = cursor.blockNumber() + 1
        else:
            s = min(cursor.selectionStart(), cursor.selectionEnd())
            e = max(cursor.selectionStart(), cursor.selectionEnd())
            # Convert document positions to 1-based line numbers
            s = self._pos_to_line(s)
            e = self._pos_to_line(e)
        self.spin_start.setValue(s)
        self.spin_end.setValue(e)
        txt = self.ed_item_text.text().strip() or "Add new line"
        self._comments.setdefault("items", []).append(
            {"file": file_rel, "line_start": int(s), "line_end": int(e), "text": txt}
        )
        self.ed_item_text.clear()
        self._refresh_comments_view()

    def delete_selected_comment(self) -> None:
        row = self.list_comments.currentRow()
        if row < 0:
            return
        try:
            del self._comments["items"][row]
        except Exception:
            pass
        self._refresh_comments_view()

    def save_comments(self) -> None:
        self._comments["general"] = self.ed_general.toPlainText()
        try:
            save_comments_json(self.reviews_dir, self._comments)
            QMessageBox.information(self, "Saved", "Comments saved to comments.json.")
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))

    # ──────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────
    def _current_rel_path(self) -> Optional[str]:
        if not self.current_file:
            return None
        try:
            rel = self.current_file.relative_to(self.worktree_dir)
        except Exception:
            return None
        return str(rel).replace("\\", "/")

    def _pos_to_line(self, pos: int) -> int:
        """Convert document character position → 1-based line number."""
        doc = self.editor.document()
        block = doc.findBlock(pos)
        return block.blockNumber() + 1


# For manual debugging
if __name__ == "__main__":
    # This debug entry assumes a layout similar to:
    #   /path/.../StudentX/paper-1/submissions/<id>/payload
    #   /path/.../StudentX/paper-1/reviews/<id>/
    app = QApplication(sys.argv)
    # Adjust these paths if you want a standalone run:
    sub = Path.cwd()  # placeholder
    rev = Path.cwd()  # placeholder
    dlg = LatexWorkspace(None, submission_dir=sub, reviews_dir=rev)
    dlg.exec()
