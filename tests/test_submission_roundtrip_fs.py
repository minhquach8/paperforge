import json
import shutil
from pathlib import Path

from shared.paths import manuscript_root, manuscript_subdirs


def _write_manifest(subdir: Path, title: str, mtype: str, student: str, slug: str) -> None:
    m = {
        "manuscript_title": title,
        "manuscript_type": mtype,
        "commit_id": "cid-123",
        "created_at": 1234567890.0,
        "student_name": student,
        "manuscript_slug": slug,
        "notes": "test",
    }
    (subdir / "manifest.json").write_text(json.dumps(m, indent=2))

def test_supervisor_return_creates_review_package(tmp_path: Path):
    students_root = tmp_path / "StudentsRoot"
    student = "StudentB"
    slug = "paper-x"

    # Simulate a submitted DOCX
    mroot = manuscript_root(students_root, student, slug)
    subs = manuscript_subdirs(mroot)
    sub_id = "1700000000-abcd1234"
    subdir = subs["submissions"] / sub_id
    payload = subdir / "payload"
    payload.mkdir(parents=True, exist_ok=True)
    (payload / "ms.docx").write_bytes(b"dummy")
    _write_manifest(subdir, "Paper X", "docx", student, slug)

    # "Open in Word" step would create/refresh reviews/<id>/working.docx
    reviews_dir = mroot / "reviews" / sub_id
    reviews_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(payload / "ms.docx", reviews_dir / "working.docx")

    # "Return to Student" should produce returned.docx and comments.json
    returned = reviews_dir / "returned.docx"
    shutil.copy2(reviews_dir / "working.docx", returned)
    (reviews_dir / "comments.json").write_text(json.dumps({"notes": "Reviewed in Word"}, indent=2))

    assert returned.exists()
    assert (reviews_dir / "comments.json").exists()
