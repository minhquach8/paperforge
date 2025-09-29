from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from time import time
from typing import Optional, Tuple

from PySide6.QtWidgets import QMessageBox, QWidget

from apps.student_app.review_viewer import ReviewData, ReviewItem, open_review_dialog

# repo
from paperrepo.repo import commit as repo_commit
from paperrepo.repo import head_commit_id, init_repo, is_repo
from paperrepo.repo import history as repo_history
from paperrepo.repo import restore as repo_restore

# shared
from shared.detect import detect_manuscript_type
from shared.due import write_return_due
from shared.events import new_submission_event, utcnow_iso, write_event
from shared.models import Manifest
from shared.osutil import open_with_default_app
from shared.paths import manuscript_root, manuscript_subdirs, slugify
from shared.timeutil import iso_to_local_str

from .data import InboxItem
from .dialogs import prompt_due_datetime, prompt_mapping


def write_minimal_paper_yaml(dst: Path, title: str, journal: str = "") -> None:
    data = {"title": title, "journal": journal, "authors": [], "status": "draft"}
    (dst / "paper.yaml").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def ensure_repo_ready(working_dir: Path) -> None:
    if not is_repo(working_dir):
        init_repo(working_dir)
    if not head_commit_id(working_dir):
        repo_commit(working_dir, message="Initial snapshot (auto)")

def ensure_mapping(parent: QWidget, working_dir: Path) -> Optional[dict]:
    from shared.config import get_mapping
    m = get_mapping(working_dir)
    if m:
        return m
    return prompt_mapping(parent, working_dir, preset=None)

def change_mapping(parent: QWidget, working_dir: Path) -> Optional[dict]:
    from shared.config import get_mapping
    current = get_mapping(working_dir) or {}
    return prompt_mapping(parent, working_dir, preset=current)

def create_submission_package(parent: QWidget, working_dir: Path, mapping: dict, commit_message: Optional[str]) -> tuple[Path, str]:
    """Create `submissions/<id>/payload` and manifest/events. Return (dest_root, submission_id)."""
    dest_root = manuscript_root(Path(mapping["students_root"]), mapping["student_name"], mapping["slug"])
    subs = manuscript_subdirs(dest_root)
    submission_id = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    dest = subs["submissions"] / submission_id
    payload = dest / "payload"; payload.mkdir(parents=True, exist_ok=True)

    for p in working_dir.rglob("*"):
        if p.is_dir(): 
            continue
        rel = p.relative_to(working_dir)
        if any(part in {".paperrepo", "submissions", "reviews", "events"} for part in rel.parts):
            continue
        (payload / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, payload / rel)

    mtype = detect_manuscript_type(payload)

    # journal (optional)
    journal_val = None
    try:
        paper_cfg = json.loads((working_dir / "paper.yaml").read_text(encoding="utf-8"))
        journal_val = (paper_cfg.get("journal") or "").strip() or None
    except Exception:
        pass

    manifest = Manifest(
        manuscript_title=working_dir.name,
        manuscript_type=mtype,
        commit_id=(head_commit_id(working_dir) or ""),
        created_at=time(),
        student_name=mapping["student_name"],
        manuscript_slug=mapping["slug"],
        notes=(commit_message if isinstance(commit_message, str) else None),
        submitted_at=utcnow_iso(),
        journal=journal_val,
    )
    (dest / "manifest.json").write_text(json.dumps(asdict(manifest), ensure_ascii=False, indent=2), encoding="utf-8")
    write_event(subs["events"], new_submission_event(submission_id))
    return dest_root, submission_id

def open_review(parent: QWidget, item: InboxItem) -> None:
    sel_path = item.file
    if not sel_path.exists():
        QMessageBox.warning(parent, "Missing file", f"Review file not found:\n{sel_path}")
        return
    folder = sel_path.parent

    def _first(glob_pat: str) -> Optional[str]:
        for p in sorted(folder.glob(glob_pat)):
            return str(p)
        return None

    pdf_path = None
    diff_pdf = _first("*diff*.pdf")
    if sel_path.suffix.lower() == ".pdf":
        pdf_path = str(sel_path)
    elif diff_pdf:
        pdf_path = diff_pdf
    else:
        pdf_path = _first("*.pdf")

    general_notes = ""
    comments_list = []
    item_objs: list[ReviewItem] = []
    cjson = item.comments_json
    if cjson.exists():
        try:
            d = json.loads(cjson.read_text(encoding="utf-8"))
            general_notes = d.get("general") or ""
            comments_list = d.get("comments") or []
            for it in (d.get("items") or []):
                f = it.get("file", "")
                ls = it.get("line_start", it.get("line", ""))
                le = it.get("line_end", ls)
                msg = it.get("text", "")
                linestr = str(ls) if ls == le else f"{ls}-{le}"
                item_objs.append(ReviewItem(file=f, lines=linestr, message=msg))
        except Exception as e:
            general_notes = f"(Failed to parse comments.json: {e})"

    build_log = ""
    for cand in ("build.log", "latexmk.log", "pdflatex.log", "log.txt"):
        p = folder / cand
        if p.exists():
            try:
                build_log = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                pass
            break

    sources: list[tuple[str, str]] = []
    texs = list(folder.glob("*.tex")) or list(folder.glob("**/*.tex"))
    for p in texs[:30]:
        sources.append((p.name, str(p)))

    review = ReviewData(
        title=f"Review — submission {item.sub_id}",
        status="Returned" if "returned" in sel_path.name.lower() else "Preview",
        pdf_path=pdf_path,
        diff_pdf_path=diff_pdf,
        general_notes=general_notes,
        comments=comments_list,
        items=item_objs,
        build_log=build_log,
        sources=sources,
    )

    if not review.pdf_path:
        for cand in ("returned.html", "review.html"):
            hp = folder / cand
            if hp.exists():
                try: open_with_default_app(hp)
                except Exception: pass
                break

    open_review_dialog(parent, review)

def pull_review_to_working( parent: QWidget, working_dir: Path, item: InboxItem) -> None:
    src = item.file
    if not src.exists():
        QMessageBox.warning(parent, "Missing file", f"Review file not found:\n{src}")
        return
    dest_dir = working_dir / "received_reviews" / item.sub_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"returned{src.suffix.lower()}"
    try:
        shutil.copy2(src, dest)
        if item.comments_json.exists():
            shutil.copy2(item.comments_json, dest_dir / "comments.json")
    except Exception as e:
        QMessageBox.critical(parent, "Save failed", str(e)); return

    resp = QMessageBox.question(
        parent,
        "Create checkpoint?",
        "A copy of the review has been saved locally.\n\n"
        "Do you want to create a checkpoint to record this in history?",
        QMessageBox.Yes | QMessageBox.No,
    )
    if resp == QMessageBox.Yes:
        try:
            repo_commit(working_dir, message=f"Save supervisor review for submission {item.sub_id}")
        except Exception:
            pass
    parent.statusBar().showMessage(f"Saved review to: {dest}", 6000)
    QMessageBox.information(parent, "Saved", f"Review saved to:\n{dest}")
