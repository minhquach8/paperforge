from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional


class ManuscriptType(str, Enum):
    DOCX = 'docx'
    LATEX = 'latex'
    MIXED = 'mixed'  # optional/future


@dataclass
class Commit:
    """A minimal commit object stored under .paperrepo/commits/<id>.json"""

    id: str
    parent: Optional[str]
    message: str
    timestamp: float
    files: Dict[str, str]  # path -> blob hash (sha256 hex)
    # NOTE: linear history for MVP, so max one parent.


@dataclass
class Manifest:
    """Submission manifest stored as JSON alongside the payload folder."""

    manuscript_title: str
    manuscript_type: ManuscriptType
    commit_id: str
    created_at: float
    student_name: str
    manuscript_slug: str
    notes: Optional[str] = None
    submitted_at: Optional[str] = None
    journal: Optional[str] = None


class EventType(str, Enum):
    NEW_SUBMISSION = 'new_submission'
    RETURNED = 'returned'


@dataclass
class Event:
    """File-based event written into <manuscript>/events/."""

    type: EventType
    submission_id: str
    actor: str  # "student" or "supervisor"
    timestamp: float

    def to_dict(self) -> dict:
        return {
            'type': self.type,
            'submission_id': self.submission_id,
            'actor': self.actor,
            'timestamp': self.timestamp,
        }


def new_submission_id() -> str:
    """Generate a sortable-ish id; timestamp-prefix plus short uuid."""
    return f'{int(time.time())}-{uuid.uuid4().hex[:8]}'
