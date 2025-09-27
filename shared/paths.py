from __future__ import annotations

import re
from pathlib import Path


def slugify(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "untitled"


def ensure_dirs(*paths: Path) -> None:
    for p in paths:
        p.mkdir(parents=True, exist_ok=True)


def student_root(students_root: Path, student_name: str) -> Path:
    return students_root / student_name


def manuscript_root(students_root: Path, student_name: str, manuscript_slug: str) -> Path:
    return student_root(students_root, student_name) / manuscript_slug


def manuscript_subdirs(base: Path) -> dict[str, Path]:
    subs = {
        "submissions": base / "submissions",
        "reviews": base / "reviews",
        "events": base / "events",
        "repo": base / ".paperrepo",
    }
    ensure_dirs(*subs.values())
    return subs


def repo_paths(manuscript_dir: Path) -> dict[str, Path]:
    repo = manuscript_dir / ".paperrepo"
    objects = repo / "objects"
    commits = repo / "commits"
    head = repo / "HEAD"
    ensure_dirs(repo, objects, commits)
    return {"repo": repo, "objects": objects, "commits": commits, "head": head}
