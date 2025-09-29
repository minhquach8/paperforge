# shared/manuscript/detect.py
from __future__ import annotations

from pathlib import Path

from shared.models import ManuscriptType


def detect_doc_kind(root: Path) -> str:
    has_docx = any(p.is_file() and p.suffix.lower() == ".docx" for p in root.rglob("*"))
    has_doc  = any(p.is_file() and p.suffix.lower() == ".doc"  for p in root.rglob("*"))
    has_tex  = any(p.is_file() and p.suffix.lower() == ".tex"  for p in root.rglob("*"))
    has_word = has_docx or has_doc
    if has_word and not has_tex: return "docx"
    if has_tex  and not has_word: return "latex"
    if has_word and has_tex:      return "docx"   # ưu tiên Word cho MVP
    return "docx"

def detect_manuscript_type(root: Path) -> ManuscriptType:
    return ManuscriptType.DOCX if detect_doc_kind(root) == "docx" else ManuscriptType.LATEX
