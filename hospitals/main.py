"""FastAPI app: JSON API over today's schedule, plus the static web UI."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

from hospitals.fetcher import now_athens
from hospitals.models import DaySchedule
from hospitals.store import get_schedule
from hospitals.windows import is_open_at

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="Attica Hospital On-Call Tracker")


def _load(refresh: bool) -> DaySchedule:
    schedule = get_schedule(refresh=refresh)
    if schedule is None:
        raise HTTPException(
            status_code=503,
            detail="Today's on-call schedule is not published yet.",
        )
    return schedule


def _now_hhmm() -> str:
    return now_athens().strftime("%H:%M")


@app.get("/api/now")
def api_now(refresh: bool = Query(False)) -> dict:
    """Everything on duty right now, grouped by specialty."""
    schedule = _load(refresh)
    now = _now_hhmm()
    groups = []
    for specialty in schedule.specialties:
        open_hospitals = [
            {"name": h.name, "window": h.window.model_dump(), "note": h.note}
            for h in specialty.hospitals
            if is_open_at(h.window, now)
        ]
        if open_hospitals:
            groups.append({"specialty": specialty.name, "hospitals": open_hospitals})
    return {"date": schedule.date, "date_greek": schedule.date_greek, "now": now, "groups": groups}


@app.get("/api/specialties")
def api_specialties(refresh: bool = Query(False)) -> dict:
    """List of specialty names for the dropdown."""
    schedule = _load(refresh)
    return {
        "date": schedule.date,
        "date_greek": schedule.date_greek,
        "specialties": [s.name for s in schedule.specialties],
    }


@app.get("/api/specialties/{name}")
def api_specialty(name: str, refresh: bool = Query(False)) -> dict:
    """Hospitals for one specialty, each flagged open_now."""
    schedule = _load(refresh)
    now = _now_hhmm()
    match = next((s for s in schedule.specialties if s.name == name), None)
    if match is None:
        raise HTTPException(status_code=404, detail=f"Unknown specialty: {name}")
    hospitals = [
        {
            "name": h.name,
            "window": h.window.model_dump(),
            "note": h.note,
            "open_now": is_open_at(h.window, now),
        }
        for h in match.hospitals
    ]
    return {"specialty": match.name, "now": now, "hospitals": hospitals}


@app.get("/api/hospitals/{name}")
def api_hospital(name: str, refresh: bool = Query(False)) -> dict:
    """Every specialty/window this hospital is on duty for today."""
    schedule = _load(refresh)
    now = _now_hhmm()
    entries = []
    for specialty in schedule.specialties:
        for hospital in specialty.hospitals:
            if hospital.name == name:
                entries.append(
                    {
                        "specialty": specialty.name,
                        "window": hospital.window.model_dump(),
                        "note": hospital.note,
                        "open_now": is_open_at(hospital.window, now),
                    }
                )
    if not entries:
        raise HTTPException(status_code=404, detail=f"Unknown hospital: {name}")
    return {"hospital": name, "now": now, "entries": entries}


@app.get("/api/health-centers")
def api_health_centers(refresh: bool = Query(False)) -> dict:
    schedule = _load(refresh)
    now = _now_hhmm()
    centers = [
        {"name": c.name, "window": c.window.model_dump(), "open_now": is_open_at(c.window, now)}
        for c in schedule.health_centers
    ]
    return {"date": schedule.date, "now": now, "health_centers": centers}


# Static web UI at "/". Mounted last so /api/* routes win.
app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
