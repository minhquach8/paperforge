from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class InboxItem:
    sub_id: str
    file: Path              # returned.docx/.doc/.html OR review.html
    label: str              # human label
    comments_json: Path
    when_label: str         # "submitted …" | "returned …"
    due_iso: Optional[str]  # UTC ISO or None
    due_label: str          # localised text or ""
    overdue: bool
