from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path
from typing import Optional, Tuple

from .tectonic_runtime import get_cache_dir, get_tectonic_path


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def detect_main_tex(root: Path) -> Optional[Path]:
    """
    Tìm main .tex trong thư mục `root`. Thử theo thứ tự phổ biến.
    Trả về path tương đối (so với root) nếu tìm thấy.
    """
    candidates = [
        "main.tex",
        "paper.tex",
        "manuscript.tex",
        "thesis.tex",
    ]
    # 1) ưu tiên ứng viên trên
    for name in candidates:
        p = root / name
        if p.exists():
            return Path(name)
    # 2) fallback: lấy file .tex có kích thước lớn nhất (đỡ trúng preamble)
    tex_files = sorted((p for p in root.rglob("*.tex") if p.is_file()), key=lambda x: x.stat().st_size, reverse=True)
    if tex_files:
        try:
            return tex_files[0].relative_to(root)
        except Exception:
            return tex_files[0].name and Path(tex_files[0].name)
    return None


def _tectonic_env() -> dict:
    """Tạo ENV chuẩn cho Tectonic (luôn là dict)."""
    env = os.environ.copy()
    cache_dir = get_cache_dir()
    env["TECTONIC_CACHE_DIR"] = str(cache_dir)
    # An toàn thêm—tránh locale issues trên Windows lab
    env.setdefault("LC_ALL", "C.UTF-8")
    env.setdefault("LANG", "C.UTF-8")
    return env


def _tectonic_cmd(workdir: Path, main_rel: Path, out_pdf: Path) -> Tuple[list[str], dict]:
    """
    Lệnh tectonic compile chuẩn (ra PDF), trả về (cmd_list, env_dict).
    """
    exe = get_tectonic_path()  # Path tới vendor/.../tectonic(.exe) hoặc 'tectonic' nếu có trên PATH
    outdir = out_pdf.parent
    outdir.mkdir(parents=True, exist_ok=True)

    # Tectonic sẽ đặt file PDF theo tên .tex => để ra đúng đích, ta dùng --outdir
    cmd = [
        str(exe),
        "-X", "compile",
        str(main_rel),          # đường dẫn tương đối so với workdir
        "--outdir", str(outdir),
        "--keep-logs",
        "--synctex",
        # Bạn có thể bật/đổi backend nếu cần:
        # "--bury-errors"   # không nên khi muốn xem log
    ]
    return cmd, _tectonic_env()


def _read_file_safely(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------
def build_pdf(workdir: Path, main_rel: Path, out_pdf: Path) -> Tuple[bool, str, Optional[Path]]:
    """
    Build PDF bằng Tectonic.
    - workdir: thư mục chứa source (cwd khi chạy)
    - main_rel: đường dẫn *.tex tương đối so với workdir
    - out_pdf: đường dẫn PDF kỳ vọng (trong cùng/khác thư mục)

    Trả về: (ok, log, produced_path|None)
    """
    workdir = workdir.resolve()
    main_rel = Path(main_rel)
    if not (workdir / main_rel).exists():
        return False, f"Main TeX not found: {(workdir / main_rel)}", None

    cmd, env = _tectonic_cmd(workdir, main_rel, out_pdf)
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(workdir),
            env=env,                     # <-- luôn là dict
            capture_output=True,
            text=True,
            check=False,
        )
        log = (proc.stdout or "") + (proc.stderr or "")
        # Kiểm tra file PDF đã có chưa (tectonic đặt theo tên main)
        produced_pdf = out_pdf
        if not produced_pdf.exists():
            # Nếu tên PDF khác (ví dụ tên của main.tex), tìm file lớn nhất trong outdir
            pdfs = sorted(out_pdf.parent.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
            if pdfs:
                produced_pdf = pdfs[0]
        if proc.returncode != 0 or not produced_pdf.exists():
            return False, f"$ {' '.join(shlex.quote(x) for x in cmd)}\n\n{log}", None
        return True, log, produced_pdf
    except FileNotFoundError:
        return False, "Tectonic executable not found. Please bundle vendor/tectonic correctly.", None
    except Exception as e:
        # lỗi như "'tuple' object has no attribute 'keys'" rơi vào đây nếu env sai kiểu
        return False, f"Failed to invoke Tectonic: {e}", None
