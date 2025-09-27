from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional, Tuple

from .tectonic_runtime import get_tectonic_path, tectonic_command_env


def which(cmd: str) -> Optional[str]:
    """Return absolute path to executable if available, else None."""
    return shutil.which(cmd)


def detect_main_tex(work_dir: Path) -> Optional[Path]:
    """
    Heuristics to pick a main .tex file relative to work_dir.
    Rules:
      - Prefer a file literally named main.tex if present.
      - Else prefer a single .tex at the root.
      - Else fall back to the lexicographically first .tex found.
      - Return a Path RELATIVE to work_dir. None if nothing found.
    """
    candidates = list(work_dir.glob("*.tex"))
    if (work_dir / "main.tex").exists():
        return Path("main.tex")
    if len(candidates) == 1:
        return candidates[0].name and Path(candidates[0].name)
    # Fallback: first .tex anywhere
    deep = sorted([p for p in work_dir.rglob("*.tex") if p.is_file()])
    if deep:
        try:
            return deep[0].relative_to(work_dir)
        except Exception:
            # If relative fails, return absolute, caller will resolve correctly
            return deep[0]
    return None


def build_pdf(work_dir: Path, main_rel: Path, out_pdf: Path) -> Tuple[bool, str, Optional[Path]]:
    """
    Build a LaTeX project using Tectonic.

    Args:
      work_dir: directory containing LaTeX sources.
      main_rel: main tex file RELATIVE to work_dir (as returned by detect_main_tex).
      out_pdf: desired output PDF path (we will move/copy to this exact path).

    Returns:
      (ok, log, produced_path):
        - ok: True on success
        - log: combined stdout/stderr of the build
        - produced_path: final PDF path on success, else None
    """
    log_chunks: list[str] = []
    try:
        tectonic = get_tectonic_path()
    except Exception as e:
        # Friendly message; caller can surface this in the UI
        return False, f"[Tectonic] {e}", None

    env = tectonic_command_env()

    # Tectonic writes outputs into an output directory, not a single filename.
    # We compile into out_pdf.parent and then rename the produced PDF into out_pdf.
    out_dir = out_pdf.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    main_abs = (work_dir / main_rel).resolve()
    if not main_abs.exists():
        return False, f"Main .tex not found: {main_abs}", None

    # Run tectonic. Compatible CLI flags:
    #   tectonic -o <outdir> <main.tex>
    # (Newer versions support `-X build`, but -o works broadly.)
    cmd = [str(tectonic), "-o", str(out_dir), str(main_abs)]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(work_dir),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        log = (proc.stdout or "") + "\n" + (proc.stderr or "")
        log_chunks.append(log)
        if proc.returncode != 0:
            return False, "\n".join(log_chunks), None
    except Exception as e:
        return False, f"Failed to invoke Tectonic: {e}", None

    # Tectonic emits a PDF named after the main file (e.g. main.pdf) into out_dir.
    produced = out_dir / (main_abs.stem + ".pdf")
    if not produced.exists():
        # Some templates may rename; try any *.pdf newer in out_dir
        pdfs = sorted([p for p in out_dir.glob("*.pdf")], key=lambda p: p.stat().st_mtime, reverse=True)
        if pdfs:
            produced = pdfs[0]
        else:
            return False, "No PDF was produced by Tectonic.", None

    if produced.resolve() != out_pdf.resolve():
        # Move/rename to the exact expected path
        try:
            if out_pdf.exists():
                out_pdf.unlink()
            produced.rename(out_pdf)
        except Exception:
            # If rename across devices fails, fall back to copy
            import shutil
            shutil.copy2(produced, out_pdf)

    return True, "\n".join(log_chunks), out_pdf