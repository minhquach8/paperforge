from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional, Tuple

from .builder import build_pdf, detect_main_tex


def which(cmd: str) -> Optional[str]:
    import shutil as _sh
    return _sh.which(cmd)


def run_latexdiff(old_main: Path, new_main: Path, out_tex: Path) -> Tuple[bool, str]:
    """
    Run latexdiff to produce a single TeX with inline highlights.
    Uses --flatten so that changes in included files are reflected.
    Returns (ok, log). The output is written to `out_tex`.
    """
    ld = which("latexdiff")
    if not ld:
        return False, "latexdiff not found on PATH. Please install TeX Live / MiKTeX 'latexdiff'."

    out_tex.parent.mkdir(parents=True, exist_ok=True)
    # Common options:
    #   --flatten: expand \input/\include
    #   --type=UNDERLINE: underline additions, strikeout deletions (readable)
    #   --math-markup=1: annotate maths where possible
    cmd = [
        ld, "--flatten", "--type=UNDERLINE", "--math-markup=1",
        str(old_main), str(new_main)
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    log = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        return False, log
    try:
        out_tex.write_text(proc.stdout, encoding="utf-8")
    except Exception as e:
        return False, f"Failed writing diff TeX: {e}"
    return True, log


def build_diff_pdf(
    payload_dir: Path,
    worktree_dir: Path,
    reviews_dir: Path,
    main_rel: Optional[Path] = None,
) -> Tuple[bool, str, Optional[Path]]:
    """
    Create a highlighted (latexdiff) PDF between original payload and edited worktree.

    Steps:
      1) Detect main.tex (or provided via main_rel).
      2) Copy worktree → reviews/<id>/diff/ (so assets are resolvable).
      3) Run latexdiff(old_main=payload/main.tex, new_main=diff/main.tex) → diff/main_diff.tex
      4) Build PDF from diff/main_diff.tex → reviews/<id>/compiled_diff.pdf

    Returns (ok, log, pdf_path or None).
    """
    if main_rel is None:
        # Try to detect main in worktree first (usually the same name as payload's main)
        main_rel = detect_main_tex(worktree_dir)
        if main_rel is None:
            main_rel = detect_main_tex(payload_dir)
        if main_rel is None:
            return False, "Cannot detect main .tex in either worktree or payload.", None

    old_main = (payload_dir / main_rel).resolve()
    new_main = (worktree_dir / main_rel).resolve()
    if not old_main.exists() or not new_main.exists():
        return False, f"Main TeX not found. Old: {old_main.exists()} New: {new_main.exists()}", None

    diff_dir = reviews_dir / "diff"
    # Refresh diff workspace: copy current worktree (assets) into diff/
    if diff_dir.exists():
        shutil.rmtree(diff_dir)
    shutil.copytree(worktree_dir, diff_dir)

    out_tex = diff_dir / "main_diff.tex"
    ok, log = run_latexdiff(old_main, diff_dir / main_rel, out_tex)
    if not ok:
        return False, log, None

    # Build to compiled_diff.pdf
    out_pdf = reviews_dir / "compiled_diff.pdf"
    ok2, log2, produced = build_pdf(diff_dir, out_tex.relative_to(diff_dir), out_pdf)
    return ok2, log + "\n" + log2, produced if ok2 else None
