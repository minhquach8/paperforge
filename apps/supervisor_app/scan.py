from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from shared.detect import detect_manuscript_type
from shared.due import is_overdue_iso, read_return_due
from shared.events import get_submission_times
from shared.models import ManuscriptType
from shared.timeutil import iso_to_local_str

from .data import SubmissionInfo


def mtype_label(t: ManuscriptType) -> str:
    return "Word" if t == ManuscriptType.DOCX else "LaTeX"

def submission_status(manuscript_root: Path, submission_id: str) -> str:
    r = manuscript_root / "reviews" / submission_id
    if (r / "returned.docx").exists() or (r / "returned.doc").exists() or (r / "returned.html").exists():
        return "Returned"
    if (r / "working.docx").exists() or (r / "working.doc").exists() or (r / "review.html").exists() \
       or (r / "compiled.pdf").exists() or (r / "compiled_diff.pdf").exists():
        return "In review"
    return "New"

def last_review_edit_iso(manuscript_root: Path, submission_id: str) -> Optional[str]:
    rdir = manuscript_root / "reviews" / submission_id
    if not rdir.exists():
        return None
    mtimes: list[float] = []
    def _add(p: Path) -> None:
        if p.exists():
            try: mtimes.append(p.stat().st_mtime)
            except Exception: pass
    for name in ("working.docx","working.doc","returned.docx","returned.doc","review.html",
                 "returned.html","compiled.pdf","compiled_diff.pdf","comments.json"):
        _add(rdir / name)
    for sub in ("worktree","diff"):
        d = rdir / sub
        if d.exists():
            for p in d.rglob("*"):
                if p.is_file(): _add(p)
    if not mtimes: return None
    latest = max(mtimes)
    return datetime.fromtimestamp(latest, tz=timezone.utc).isoformat(timespec="minutes").replace("+00:00","Z")

def _read_title_and_journal(manifest_path: Path, payload: Path, title_default: str) -> tuple[str, str]:
    title = title_default
    journal = ""
    try:
        mf = json.loads(manifest_path.read_text(encoding="utf-8"))
        title = mf.get("manuscript_title", title)
        journal = (mf.get("journal") or "").strip()
    except Exception:
        pass
    if not journal:
        try:
            py = json.loads((payload / "paper.yaml").read_text(encoding="utf-8"))
            journal = (py.get("journal") or "").strip()
        except Exception:
            journal = ""
    return title, journal

def build_when_label(submitted_iso: Optional[str], returned_iso: Optional[str]) -> str:
    if returned_iso:
        return f"returned {iso_to_local_str(returned_iso)}"
    if submitted_iso:
        return f"submitted {iso_to_local_str(submitted_iso)}"
    return ""

def scan_students_root(root: Path, *,
                       text_query: str = "",
                       status_filter: str = "All",
                       type_filter: str = "All") -> list[SubmissionInfo]:
    results: list[SubmissionInfo] = []
    q = (text_query or "").strip().lower()

    for student_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for manuscript_dir in sorted(p for p in student_dir.iterdir() if p.is_dir()):
            subs_dir = manuscript_dir / "submissions"
            if not subs_dir.exists():
                continue
            title_default = manuscript_dir.name
            for subdir in sorted(p for p in subs_dir.iterdir() if p.is_dir()):
                manifest_path = subdir / "manifest.json"
                if not manifest_path.exists():
                    continue
                payload = subdir / "payload"
                mtype = detect_manuscript_type(payload)
                status = submission_status(manuscript_dir, subdir.name)
                # times
                events_dir = manuscript_dir / "events"
                sub_iso, ret_iso = get_submission_times(events_dir, subdir.name)
                if not sub_iso:
                    try:
                        mf = json.loads(manifest_path.read_text(encoding="utf-8"))
                        sub_iso = mf.get("submitted_at")
                    except Exception:
                        pass
                last_iso = last_review_edit_iso(manuscript_dir, subdir.name)
                # title/journal
                title, journal = _read_title_and_journal(manifest_path, payload, title_default)

                # filters
                if q:
                    blob = " ".join([student_dir.name, title, journal, subdir.name]).lower()
                    if q not in blob:
                        continue
                if status_filter != "All" and status != status_filter:
                    continue
                if type_filter != "All" and mtype_label(mtype) != type_filter:
                    continue

                rdir = manuscript_dir / "reviews" / subdir.name
                # due
                due_data = read_return_due(manuscript_dir, subdir.name)
                due_iso = (due_data.get("return_due") or "").strip() or None
                due_note = (due_data.get("note") or "").strip()
                overdue = bool(due_iso) and is_overdue_iso(due_iso)

                info = SubmissionInfo(
                    student=student_dir.name,
                    manuscript_root=manuscript_dir,
                    manuscript_title=title,
                    journal=journal,
                    submission_id=subdir.name,
                    payload_dir=payload,
                    reviews_dir=rdir,
                    mtype=mtype,
                    status=status,
                    submitted_iso=sub_iso,
                    returned_iso=ret_iso,
                    when_label=build_when_label(sub_iso, ret_iso),
                    last_edit_iso=last_iso,
                    due_iso=due_iso,
                    due_note=due_note,
                    overdue=overdue,
                )
                results.append(info)
    return results
