from __future__ import annotations

from typing import Optional, Tuple

from PySide6.QtCore import QDateTime, Qt
from PySide6.QtWidgets import (
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)


def prompt_due_datetime(parent: QWidget, *, title: str = "Set expected return date",
                        note_default: str = "") -> tuple[Optional[str], str]:
    d = QDialog(parent); d.setWindowTitle(title)
    lay = QVBoxLayout(d)
    lay.addWidget(QLabel("Student expected to return by:"))
    dtw = QDateTimeEdit(QDateTime.currentDateTime().addDays(7), d)
    dtw.setCalendarPopup(True)
    dtw.setDisplayFormat("yyyy-MM-dd HH:mm")
    lay.addWidget(dtw)
    lay.addWidget(QLabel("Note (optional):"))
    ed_note = QLineEdit(note_default, d)
    lay.addWidget(ed_note)
    btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=d)
    lay.addWidget(btns)
    btns.accepted.connect(d.accept); btns.rejected.connect(d.reject)
    if d.exec() == QDialog.Accepted:
        iso = dtw.dateTime().toUTC().toString(Qt.ISODate)  # “…Z”
        return iso, ed_note.text().strip()
    return None, ""
