from pathlib import Path

from shared.events import list_events, new_submission_event, returned_event, write_event
from shared.paths import manuscript_root, manuscript_subdirs


def test_paths_and_events(tmp_path: Path):
    students_root = tmp_path / "StudentsRoot"
    student = "StudentA"
    slug = "paper-1"

    mroot = manuscript_root(students_root, student, slug)
    subs = manuscript_subdirs(mroot)

    for key in ("submissions", "reviews", "events", "repo"):
        assert subs[key].exists()

    # Write a pair of events
    e1 = write_event(subs["events"], new_submission_event("1234-aaaa"))
    e2 = write_event(subs["events"], returned_event("1234-aaaa"))
    assert e1.exists() and e2.exists()

    # Newest-first listing, filter by type
    all_events = list_events(subs["events"])
    assert all_events and all_events[0]["type"] in {"returned", "new_submission"}

    returned_only = list_events(subs["events"], kinds=["returned"])
    assert returned_only and all(ev["type"] == "returned" for ev in returned_only)
