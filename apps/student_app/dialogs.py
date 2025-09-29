from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from PySide6.QtCore import QDateTime, Qt
from PySide6.QtWidgets import (
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from shared.config import get_defaults, remember_defaults, remember_mapping
from shared.paths import slugify


def prompt_due_datetime(parent: QWidget, *, title="Set my expected date",
                        note_default="") -> tuple[Optional[str], str]:
    d = QDialog(parent); d.setWindowTitle(title)
    lay = QVBoxLayout(d)
    lay.addWidget(QLabel("I expect to send my revision by:"))
    dtw = QDateTimeEdit(QDateTime.currentDateTime().addDays(7), d)
    dtw.setCalendarPopup(True); dtw.setDisplayFormat("yyyy-MM-dd HH:mm")
    lay.addWidget(dtw)
    lay.addWidget(QLabel("Note (optional):"))
    ed_note = QLineEdit(note_default, d); lay.addWidget(ed_note)
    btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=d)
    lay.addWidget(btns)
    btns.accepted.connect(d.accept); btns.rejected.connect(d.reject)
    if d.exec() == QDialog.Accepted:
        iso = dtw.dateTime().toUTC().toString(Qt.ISODate)  # “…Z”
        return iso, ed_note.text().strip()
    return None, ""

def prompt_mapping(parent: QWidget, working_dir: Path, preset: Optional[dict] = None) -> Optional[dict]:
    """Ask user for Students' Root / Student name / Manuscript slug and save mapping."""
    defaults = get_defaults()
    start_dir = (preset or {}).get("students_root") or defaults.get("students_root") or ""
    students_root_dir = QFileDialog.getExistingDirectory(parent, "Select Students’ Root (OneDrive)", dir=start_dir)
    if not students_root_dir:
        return None

    student_name_default = (preset or {}).get("student_name") or defaults.get("student_name") or ""
    student_name, ok = QInputDialog.getText(parent, "Student name",
                                            "Enter your display name (as used by the supervisor):",
                                            text=student_name_default)
    if not ok or not (student_name or "").strip():
        return None

    slug_default = (preset or {}).get("slug") or slugify(working_dir.name)
    manuscript_slug, ok = QInputDialog.getText(parent, "Manuscript slug",
                                               "Slug for this manuscript folder:",
                                               text=slug_default)
    if not ok or not (manuscript_slug or "").strip():
        return None

    manuscript_slug = slugify(manuscript_slug)
    remember_defaults(students_root_dir, student_name.strip())
    remember_mapping(working_dir, students_root_dir, student_name.strip(), manuscript_slug)
    return {"students_root": students_root_dir, "student_name": student_name.strip(), "slug": manuscript_slug}
