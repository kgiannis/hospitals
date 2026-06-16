"""JSON cache and the get_schedule() orchestrator."""

from __future__ import annotations

from pathlib import Path

from hospitals.fetcher import download_pdf, fetch_listing, find_today_pdf, now_athens
from hospitals.models import DaySchedule
from hospitals.parser import parse_pdf

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def get_schedule(refresh: bool = False) -> DaySchedule | None:
    """Return today's schedule from cache, or fetch+parse+cache it.

    Returns None if today's PDF is not published yet. The downloaded PDF is
    always deleted; only the derived JSON is persisted.
    """
    now = now_athens()
    date_str = now.strftime("%Y-%m-%d")
    cache_path = DATA_DIR / f"{date_str}.json"

    if cache_path.exists() and not refresh:
        return DaySchedule.model_validate_json(cache_path.read_text(encoding="utf-8"))

    found = find_today_pdf(fetch_listing(), now)
    if found is None:
        return None
    fdl, date_greek = found

    pdf_path = download_pdf(fdl)
    try:
        schedule = parse_pdf(
            pdf_path,
            date_str=date_str,
            date_greek=date_greek,
            source_fdl=fdl,
            fetched_at=now.isoformat(),
        )
    finally:
        pdf_path.unlink(missing_ok=True)

    DATA_DIR.mkdir(exist_ok=True)
    cache_path.write_text(schedule.model_dump_json(indent=2), encoding="utf-8")
    return schedule
