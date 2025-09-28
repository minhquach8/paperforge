# shared/version.py
from __future__ import annotations

import os

# CI (GitHub Actions) sẽ set PAPERFORGE_VERSION, fallback khi chạy local
APP_VERSION = os.getenv("PAPERFORGE_VERSION", "1.0.0")
GITHUB_REPO = os.getenv("PAPERFORGE_REPO", "minhquach8/paperforge")
