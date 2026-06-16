"""Parse Greek time-window strings and test whether a window is open now."""

from __future__ import annotations

import re

from hospitals.models import Window

_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})")


def _to_minutes(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def parse_window_text(text: str) -> Window | None:
    """Parse a column header / cell time range into a Window.

    Handles forms like "08:00 – 14:30", "14:30 – 08:00 επομένης",
    "08:00 – 08:00 επομένης". Returns None if two times are not found.
    The window crosses midnight when "επομέν…" appears or when start >= end.
    """
    times = _TIME_RE.findall(text)
    if len(times) < 2:
        return None
    start = f"{int(times[0][0]):02d}:{times[0][1]}"
    end = f"{int(times[1][0]):02d}:{times[1][1]}"
    crosses = "επομέν" in text.lower() or _to_minutes(start) >= _to_minutes(end)
    return Window(start=start, end=end, crosses_midnight=crosses)


def is_open_at(window: Window, now_hhmm: str) -> bool:
    """True if ``now_hhmm`` ("HH:MM") falls inside the window."""
    now = _to_minutes(now_hhmm)
    start = _to_minutes(window.start)
    end = _to_minutes(window.end)
    if window.crosses_midnight:
        # 08:00->08:00 (start == end) means 24h: always open.
        if start == end:
            return True
        return now >= start or now <= end
    return start <= now <= end
