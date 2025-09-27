import json
import time
from pathlib import Path

# Try to import helpers from apps if available; otherwise skip gracefully.
import pytest

student_mod = pytest.importorskip("apps.student_app.main")
supervisor_mod = pytest.importorskip("apps.supervisor_app.main")

def _make_payload_with_files(root: Path, names: list[str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for name in names:
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"dummy")

def test_detect_types_docx_doc_tex(tmp_path: Path):
    # DOCX only
    p1 = tmp_path / "p1"
    _make_payload_with_files(p1, ["manuscript.docx"])
    assert student_mod.detect_manuscript_type(p1).value == "docx"
    assert supervisor_mod.detect_type_from_payload(p1) == "docx"

    # DOC only
    p2 = tmp_path / "p2"
    _make_payload_with_files(p2, ["legacy.doc"])
    assert student_mod.detect_manuscript_type(p2).value == "docx"
    assert supervisor_mod.detect_type_from_payload(p2) == "docx"

    # TEX only
    p3 = tmp_path / "p3"
    _make_payload_with_files(p3, ["paper.tex", "sections/intro.tex"])
    assert student_mod.detect_manuscript_type(p3).value == "latex"
    assert supervisor_mod.detect_type_from_payload(p3) == "latex"

    # Mixed → prefer DOCX flow
    p4 = tmp_path / "p4"
    _make_payload_with_files(p4, ["paper.tex", "manuscript.docx"])
    assert student_mod.detect_manuscript_type(p4).value == "docx"
    assert supervisor_mod.detect_type_from_payload(p4) == "docx"

def test_manifest_content(tmp_path: Path):
    # Simulate Student submit writing manifest.json using the detection
    payload = tmp_path / "payload"
    _make_payload_with_files(payload, ["main.docx"])

    mtype = student_mod.detect_manuscript_type(payload).value
    manifest = {
        "manuscript_title": "dummy",
        "manuscript_type": mtype,
        "commit_id": "deadbeef",
        "created_at": time.time(),
        "student_name": "StudentA",
        "manuscript_slug": "paper-1",
        "notes": "unit test",
    }
    dest = tmp_path / "manifest.json"
    dest.write_text(json.dumps(manifest, indent=2))
    loaded = json.loads(dest.read_text())
    assert loaded["manuscript_type"] == "docx"
