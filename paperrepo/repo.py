from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Dict, Iterable

from shared.models import Commit
from shared.paths import repo_paths

from .storage.cas import get_bytes, put_file

# Files/folders we ignore for snapshots and when cleaning working trees
DEFAULT_IGNORES = {".paperrepo", "submissions", "reviews", "events", "__pycache__", ".DS_Store"}


def is_repo(manuscript_dir: Path) -> bool:
    return (manuscript_dir / ".paperrepo").exists()


def init_repo(manuscript_dir: Path) -> None:
    rp = repo_paths(manuscript_dir)
    rp["repo"].mkdir(parents=True, exist_ok=True)
    rp["objects"].mkdir(parents=True, exist_ok=True)
    rp["commits"].mkdir(parents=True, exist_ok=True)
    if not rp["head"].exists():
        rp["head"].write_text("")  # empty means no commits yet


def _iter_files(root: Path, ignores: set[str]) -> Iterable[Path]:
    """
    Iterate all regular files under root, skipping any path that includes
    a directory name listed in 'ignores'.
    """
    for p in root.rglob("*"):
        if p.is_dir():
            continue
        rel_parts = p.relative_to(root).parts
        if any(part in ignores for part in rel_parts):
            continue
        if p.name in ignores:
            continue
        yield p


def _hash_commit(parent: str | None, message: str, timestamp: float, files: Dict[str, str]) -> str:
    obj = {
        "parent": parent or "",
        "message": message,
        "timestamp": f"{timestamp:.6f}",
        "files": files,
    }
    data = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def commit(manuscript_dir: Path, message: str, extra_ignores: set[str] | None = None) -> Commit:
    """
    Create a linear commit: snapshot working tree (excluding .paperrepo and a small ignore set).
    """
    if not is_repo(manuscript_dir):
        init_repo(manuscript_dir)

    rp = repo_paths(manuscript_dir)
    head = rp["head"].read_text().strip() or None

    ignores = set(DEFAULT_IGNORES)
    if extra_ignores:
        ignores |= set(extra_ignores)

    files_map: Dict[str, str] = {}
    for p in _iter_files(manuscript_dir, ignores):
        rel = p.relative_to(manuscript_dir).as_posix()
        digest = put_file(rp["objects"], p)
        files_map[rel] = digest

    ts = time.time()
    cid = _hash_commit(head, message, ts, files_map)
    commit_obj = Commit(id=cid, parent=head, message=message, timestamp=ts, files=files_map)

    # Persist commit object
    (rp["commits"] / f"{cid}.json").write_text(json.dumps(asdict(commit_obj), ensure_ascii=False, indent=2))
    rp["head"].write_text(cid)
    return commit_obj


def head_commit_id(manuscript_dir: Path) -> str | None:
    rp = repo_paths(manuscript_dir)
    val = rp["head"].read_text().strip() if rp["head"].exists() else ""
    return val or None


def read_commit(manuscript_dir: Path, commit_id: str) -> Commit:
    rp = repo_paths(manuscript_dir)
    data = json.loads((rp["commits"] / f"{commit_id}.json").read_text())
    return Commit(**data)


def history(manuscript_dir: Path, limit: int | None = None) -> list[Commit]:
    """
    Walk back from HEAD following parent pointers. Linear history only.
    Returns commits newest-first.
    """
    commits: list[Commit] = []
    cur = head_commit_id(manuscript_dir)
    while cur:
        c = read_commit(manuscript_dir, cur)
        commits.append(c)
        if limit and len(commits) >= limit:
            break
        cur = c.parent
    return commits


# ─────────────────────────────────────────────────────────────────────────────
# Restore / Rollback
# ─────────────────────────────────────────────────────────────────────────────

def _clean_working_tree(manuscript_dir: Path, ignores: set[str]) -> int:
    """
    Remove all files under manuscript_dir except those within ignored folders.
    Returns the number of files removed. Directories are pruned if empty.
    """
    removed = 0
    for p in list(manuscript_dir.rglob("*"))[::-1]:  # reverse so files before dirs
        rel_parts = p.relative_to(manuscript_dir).parts
        if any(part in ignores for part in rel_parts):
            continue
        try:
            if p.is_file():
                p.unlink()
                removed += 1
            elif p.is_dir():
                # Attempt to remove empty directories; ignore errors
                p.rmdir()
        except Exception:
            pass
    return removed


def restore(manuscript_dir: Path, commit_id: str, clean: bool = False) -> int:
    """
    Restore the working tree to the content of 'commit_id'.
    - If clean=True, any existing non-ignored files will be removed first.
    - Returns the number of files written.

    This is a destructive operation on the working copy; callers should
    prompt the user before proceeding.
    """
    if not is_repo(manuscript_dir):
        raise RuntimeError("Not a repository. Initialise first.")

    rp = repo_paths(manuscript_dir)
    c = read_commit(manuscript_dir, commit_id)

    if clean:
        _clean_working_tree(manuscript_dir, DEFAULT_IGNORES)

    written = 0
    for rel_path, digest in c.files.items():
        dst = manuscript_dir / rel_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        data = get_bytes(rp["objects"], digest)
        dst.write_bytes(data)
        written += 1

    # Move HEAD to this commit as well (like a checkout)
    rp["head"].write_text(c.id)
    return written
