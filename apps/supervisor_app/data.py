from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from shared.models import ManuscriptType


@dataclass
class SubmissionInfo:
    student: str
    manuscript_root: Path
    manuscript_title: str
    journal: str
    submission_id: str
    payload_dir: Path
    reviews_dir: Path
    mtype: ManuscriptType
    status: str  # "New" | "In review" | "Returned"
    submitted_iso: Optional[str]
    returned_iso: Optional[str]
    when_label: str
    last_edit_iso: Optional[str]
    due_iso: Optional[str]
    due_note: str
    overdue: bool  # computed from due_iso
