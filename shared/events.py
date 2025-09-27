from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# Time helpers
# ─────────────────────────────────────────────────────────────────────────────
def utcnow_iso() -> str:
    """UTC now in ISO-8601 with Z (e.g. 2025-09-27T14:03:21Z)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _normalise_iso(ts: str) -> str:
    """Accept 'Z' or '+00:00' forms; return canonical Z form."""
    if ts.endswith("+00:00"):
        return ts[:-6] + "Z"
    return ts


# ─────────────────────────────────────────────────────────────────────────────
# Event schema
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Event:
    type: str                          # 'submitted' | 'returned' | ...
    submission_id: str
    actor: str                         # 'student' | 'supervisor'
    ts: str                            # ISO-8601 UTC ('...Z')
    data: Dict[str, Any]               # free-form payload

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["ts"] = _normalise_iso(d["ts"])
        return d


# ─────────────────────────────────────────────────────────────────────────────
# Factory functions
# ─────────────────────────────────────────────────────────────────────────────
def new_submission_event(submission_id: str, *, title: str = "", actor: str = "student", ts: Optional[str] = None) -> Dict[str, Any]:
    """Create a 'submitted' event."""
    return Event(
        type="submitted",
        submission_id=submission_id,
        actor=actor,
        ts=_normalise_iso(ts or utcnow_iso()),
        data={"title": title},
    ).to_dict()


def returned_event(submission_id: str, *, actor: str = "supervisor", ts: Optional[str] = None) -> Dict[str, Any]:
    """Create a 'returned' event."""
    return Event(
        type="returned",
        submission_id=submission_id,
        actor=actor,
        ts=_normalise_iso(ts or utcnow_iso()),
        data={},
    ).to_dict()


# ─────────────────────────────────────────────────────────────────────────────
# IO helpers
# ─────────────────────────────────────────────────────────────────────────────
def write_event(events_dir: Path, event: Dict[str, Any]) -> Path:
    """
    Persist event as JSON. File name is prefixed with timestamp for ordering:
      events/evt_20250927T140321Z_returned_<id>.json
    Back-compat: if event lacks 'ts', we add it now.
    """
    events_dir.mkdir(parents=True, exist_ok=True)
    ts = _normalise_iso(event.get("ts") or utcnow_iso())
    etype = event.get("type", "event")
    sid = event.get("submission_id", "unknown")
    # Collation-friendly stamp: YYYYMMDDThhmmssZ (no separators)
    stamp = ts.replace("-", "").replace(":", "")
    fname = f"evt_{stamp}_{etype}_{sid}.json"
    path = events_dir / fname
    event = dict(event)
    event["ts"] = ts
    path.write_text(json.dumps(event, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _iter_event_files(events_dir: Path) -> Iterable[Path]:
    if not events_dir.exists():
        return []
    return sorted(events_dir.glob("*.json"))


def read_events(events_dir: Path) -> List[Dict[str, Any]]:
    """Read all events (any schema); missing 'ts' will be None."""
    out: List[Dict[str, Any]] = []
    for fp in _iter_event_files(events_dir):
        try:
            obj = json.loads(fp.read_text(encoding="utf-8"))
            if "ts" in obj and isinstance(obj["ts"], str):
                obj["ts"] = _normalise_iso(obj["ts"])
            out.append(obj)
        except Exception:
            continue
    # Sort by ts if available, else by filename
    def _key(e: Dict[str, Any]) -> str:
        ts = e.get("ts")
        if isinstance(ts, str):
            return ts
        return fp.name  # type: ignore[name-defined]
    return sorted(out, key=_key)


def get_submission_times(events_dir: Path, submission_id: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Return (submitted_ts, returned_ts) in ISO UTC for a given submission_id.
    If multiple, pick earliest 'submitted' and latest 'returned'.
    """
    submitted: Optional[str] = None
    returned: Optional[str] = None
    for ev in read_events(events_dir):
        if ev.get("submission_id") != submission_id:
            continue
        et = ev.get("type")
        ts = ev.get("ts")
        if et == "submitted":
            if submitted is None or (ts and ts < submitted):
                submitted = ts
        elif et == "returned":
            if returned is None or (ts and ts > returned):
                returned = ts
    return submitted, returned
