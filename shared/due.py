# shared/due.py
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# due.json format (per submission):
# {
#   "return_due": "2025-10-04T23:59:00Z",   # ISO 8601 (UTC) — mốc student dự kiến trả lại
#   "note": "first revision",
#   "set_by": "student|supervisor",
#   "set_at": "ISO timestamp"
# }

def _file(manuscript_root: Path, submission_id: str) -> Path:
    return manuscript_root / "reviews" / submission_id / "due.json"

def read_return_due(manuscript_root: Path, submission_id: str) -> dict:
    p = _file(manuscript_root, submission_id)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

def write_return_due(
    manuscript_root: Path,
    submission_id: str,
    due_iso_utc: Optional[str],       # None => clear
    note: str = "",
    set_by: str = "",
) -> dict:
    p = _file(manuscript_root, submission_id)
    data = read_return_due(manuscript_root, submission_id)
    if due_iso_utc:
        data["return_due"] = due_iso_utc
        data["note"] = note or ""
        data["set_by"] = set_by or ""
        data["set_at"] = datetime.now(timezone.utc).isoformat()
    else:
        # clear
        for k in ("return_due", "note", "set_by", "set_at"):
            data.pop(k, None)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data

def _parse_iso(s: str) -> Optional[datetime]:
    try:
        # accept ...Z
        if s.endswith("Z"):
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        return datetime.fromisoformat(s)
    except Exception:
        return None

def is_overdue_iso(iso_str: Optional[str]) -> bool:
    if not iso_str:
        return False
    dt = _parse_iso(iso_str)
    if not dt:
        return False
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return now > dt
