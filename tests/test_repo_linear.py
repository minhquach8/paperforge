import os
from pathlib import Path

from paperrepo.repo import commit, history, init_repo, is_repo, restore


def write(p: Path, content: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")

def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")

def test_repo_init_commit_history_restore(tmp_path: Path):
    # Arrange: a minimal manuscript
    w = tmp_path / "paper-1"
    w.mkdir()
    init_repo(w)
    assert is_repo(w)

    # Create initial files
    a = w / "intro.txt"
    b = w / "data/table.csv"
    write(a, "hello v1")
    write(b, "col1,col2\n1,2\n")

    c1 = commit(w, "initial")
    hist1 = history(w)
    assert hist1 and hist1[0].id == c1.id

    # Mutate files for a second commit
    write(a, "hello v2")
    write(w / "notes.md", "draft notes")
    c2 = commit(w, "update intro and notes")

    # Assert history order (newest first)
    hist2 = history(w)
    assert [h.id for h in hist2] == [c2.id, c1.id]

    # Overlay restore to first commit (do not clean)
    # Should overwrite tracked files but keep unrelated ones (e.g., notes.md)
    written = restore(w, commit_id=c1.id, clean=False)
    assert written >= 2
    assert read(a) == "hello v1"
    assert (w / "notes.md").exists()  # overlay keeps unrelated files

    # Clean restore to second commit (remove everything except ignored dirs)
    written2 = restore(w, commit_id=c2.id, clean=True)
    assert written2 >= 2
    assert read(a) == "hello v2"
    # 'notes.md' tracked in c2, so it must exist
    assert (w / "notes.md").exists()
