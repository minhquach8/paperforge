from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def iso_to_local_str(ts: Optional[str], fmt: str = "%Y-%m-%d %H:%M") -> str:
    """
    Convert ISO-8601 UTC ('...Z' or '+00:00') to local time string.
    Returns '—' if ts is falsy or invalid.
    """
    if not ts:
        return "—"
    try:
        s = ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone().strftime(fmt)
    except Exception:
        return "—"
