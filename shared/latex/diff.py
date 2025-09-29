from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Tuple

from .builder import build_pdf, detect_main_tex


def which(cmd: str) -> Optional[str]:
    import shutil as _sh
    return _sh.which(cmd)

# ---------- Simple fallback highlighter ----------
_TOKEN_RE = re.compile(
    r"""(\\[A-Za-z@]+|\\\S|\\begin\{.*?\}|\\end\{.*?\}|\{|\}|\s+|[A-Za-z0-9]+|.)""",
    re.VERBOSE | re.DOTALL,
)

def _read_text_guess(p: Path) -> str:
    for enc in ("utf-8", "latin-1"):
        try:
            return p.read_text(encoding=enc)
        except Exception:
            pass
    return ""

def _tokenise(s: str) -> list[str]:
    return [m.group(0) for m in _TOKEN_RE.finditer(s)]

def _inject_preamble(tex: str) -> str:
    inject = (
        "% --- SimpleDiff injected ---\n"
        "\\usepackage[normalem]{ulem}\n"
        "\\usepackage{xcolor}\n"
        "\\newcommand{\\added}[1]{\\textcolor{blue}{#1}}\n"
        "\\newcommand{\\deleted}[1]{\\textcolor{red}{\\sout{#1}}}\n"
    )
    i = tex.find("\\begin{document}")
    if i == -1:
        return inject + "\n" + tex
    if "SimpleDiff injected" in tex:
        return tex
    return tex[:i] + inject + tex[i:]

def _simplediff_body(old_body: str, new_body: str) -> str:
    import difflib as _dl
    a, b = _tokenise(old_body), _tokenise(new_body)
    out: list[str] = []
    for tag, i1, i2, j1, j2 in _dl.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if tag == "equal":
            out.extend(b[j1:j2])
        elif tag == "insert":
            seg = "".join(b[j1:j2]).strip("\n")
            if seg: out.append("{\\added{" + seg + "}}")
        elif tag == "delete":
            seg = "".join(a[i1:i2]).strip("\n")
            if seg: out.append("{\\deleted{" + seg + "}}")
        else:
            del_seg = "".join(a[i1:i2]).strip("\n")
            ins_seg = "".join(b[j1:j2]).strip("\n")
            if del_seg: out.append("{\\deleted{" + del_seg + "}}")
            if ins_seg: out.append("{\\added{" + ins_seg + "}}")
    return "".join(out)

def run_simplediff(old_main: Path, new_main: Path, out_tex: Path) -> Tuple[bool, str]:
    try:
        old_src, new_src = _read_text_guess(old_main), _read_text_guess(new_main)
        if not new_src:
            return False, "New TeX empty or unreadable."
        mark = "\\begin{document}"
        if mark in old_src and mark in new_src:
            _, old_body = old_src.split(mark, 1)
            new_pre, new_body = new_src.split(mark, 1)
            body = _simplediff_body(old_body, new_body)
            combined = new_pre + mark + body
        else:
            combined = _simplediff_body(old_src, new_src)
        combined = _inject_preamble(combined)
        out_tex.parent.mkdir(parents=True, exist_ok=True)
        out_tex.write_text(combined, encoding="utf-8")
        return True, "SimpleDiff fallback used (latexdiff not found)."
    except Exception as e:
        return False, f"SimpleDiff failed: {e}"

# ---------- latexdiff first; fallback next ----------
def _patch_latexdiff_output(text: str) -> str:
    if "\\DIFadd" in text:
        return text
    patch = r"""
% --- Paperforge latexdiff preamble hardening ---
\RequirePackage[normalem]{ulem}
\RequirePackage{xcolor}
\providecommand{\DIFadd}[1]{{\protect\color{blue}\uwave{#1}}}
\providecommand{\DIFdel}[1]{{\protect\color{red}\sout{#1}}}
"""
    m = re.search(r"(\\documentclass\[.*?\]\{.*?\}|\\documentclass\{.*?\})", text, re.DOTALL)
    if m:
        return text[:m.end()] + "\n" + patch + text[m.end():]
    return patch + "\n" + text

def run_latexdiff(old_main: Path, new_main: Path, out_tex: Path) -> Tuple[bool, str]:
    ld = which("latexdiff")
    if not ld:
        return run_simplediff(old_main, new_main, out_tex)

    out_tex.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ld, "--flatten", "--allow-spaces",
        "--type=UNDERLINE", "--math-markup=2",
        str(old_main), str(new_main),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    log = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0 or not proc.stdout:
        ok2, log2 = run_simplediff(old_main, new_main, out_tex)
        return ok2, (log + "\n" + (log2 or ""))
    try:
        out_tex.write_text(_patch_latexdiff_output(proc.stdout), encoding="utf-8")
    except Exception as e:
        return False, f"Failed writing diff TeX: {e}"
    return True, log

def build_diff_pdf(
    payload_dir: Path, worktree_dir: Path, reviews_dir: Path, main_rel: Optional[Path] = None,
) -> Tuple[bool, str, Optional[Path]]:
    if main_rel is None:
        main_rel = detect_main_tex(worktree_dir) or detect_main_tex(payload_dir)
        if main_rel is None:
            return False, "Cannot detect main .tex in either worktree or payload.", None

    old_main = (payload_dir / main_rel).resolve()
    new_main = (worktree_dir / main_rel).resolve()
    if not old_main.exists() or not new_main.exists():
        return False, f"Main TeX not found. Old:{old_main.exists()} New:{new_main.exists()}", None

    diff_dir = reviews_dir / "diff"
    if diff_dir.exists():
        shutil.rmtree(diff_dir)
    shutil.copytree(worktree_dir, diff_dir)

    out_tex = diff_dir / "main_diff.tex"
    ok, log = run_latexdiff(old_main, diff_dir / main_rel, out_tex)
    if not ok:
        return False, log, None

    out_pdf = reviews_dir / "compiled_diff.pdf"
    ok2, log2, produced = build_pdf(diff_dir, out_tex.relative_to(diff_dir), out_pdf)
    return ok2, (log + "\n" + (log2 or "")), (produced if ok2 else None)
