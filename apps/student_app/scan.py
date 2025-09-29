from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, Tuple

from shared.due import is_overdue_iso, read_return_due
from shared.events import get_submission_times
from shared.timeutil import iso_to_local_str

from .data import InboxItem


def _pick_target_file(subdir: Path) -> tuple[Optional[Path], Optional[str]]:
    docx = subdir / "returned.docx"
    doc  = subdir / "returned.doc"
    rhtml = subdir / "returned.html"
    html  = subdir / "review.html"
    if docx.exists():  return docx, "returned.docx"
    if doc.exists():   return doc,  "returned.doc"
    if rhtml.exists(): return rhtml, "returned.html"
    if html.exists():  return html,  "review.html"
    return None, None

def scan_inbox(manuscript_root: Path) -> list[InboxItem]:
    """Scan `…/reviews/*` and build inbox rows."""
    reviews = manuscript_root / "reviews"
    events_dir = manuscript_root / "events"
    out: list[InboxItem] = []
    if not reviews.exists():
        return out

    for subdir in sorted((p for p in reviews.iterdir() if p.is_dir()),
                         key=lambda p: p.name, reverse=True):
        sub_id = subdir.name
        target, label = _pick_target_file(subdir)
        if not target:
            continue

        sub_ts, ret_ts = get_submission_times(events_dir, sub_id)
        when_label = ""
        if ret_ts:
            when_label = f"returned {iso_to_local_str(ret_ts)}"
        elif sub_ts:
            when_label = f"submitted {iso_to_local_str(sub_ts)}"

        # due (optional)
        due_data = read_return_due(manuscript_root, sub_id)
        raw_iso = (due_data.get("return_due") or "").strip()
        due_label = ""
        overdue = False
        if raw_iso:
            try:
                due_label = iso_to_local_str(raw_iso)
                overdue = is_overdue_iso(raw_iso)
            except Exception:
                due_label = raw_iso

        out.append(
            InboxItem(
                sub_id=sub_id,
                file=target,
                label=label or target.name,
                comments_json=target.parent / "comments.json",
                when_label=when_label,
                due_iso=(raw_iso or None),
                due_label=due_label,
                overdue=overdue,
            )
        )
    return out
