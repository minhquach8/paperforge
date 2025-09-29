# shared/osutil.py
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def open_with_default_app(path: Path) -> None:
    if sys.platform.startswith("win"):
        import os
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)
