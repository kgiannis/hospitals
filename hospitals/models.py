"""Pydantic models describing a day's parsed on-call schedule."""

from __future__ import annotations

from pydantic import BaseModel


class Window(BaseModel):
    """A time window. ``crosses_midnight`` is True when the window spans
    midnight (start >= end), e.g. 14:30 -> 08:00."""

    start: str  # "HH:MM"
    end: str  # "HH:MM"
    crosses_midnight: bool


class Hospital(BaseModel):
    name: str
    window: Window
    note: str | None = None  # inline override text, e.g. "έως 22:00"


class Specialty(BaseModel):
    name: str
    hospitals: list[Hospital]


class HealthCenter(BaseModel):
    name: str
    window: Window


class DaySchedule(BaseModel):
    date: str  # "YYYY-MM-DD"
    date_greek: str  # e.g. "ΤΕΤΑΡΤΗ 17 ΙΟΥΝΙΟΥ 2026"
    source_fdl: int
    fetched_at: str  # ISO 8601 with Athens offset
    specialties: list[Specialty]
    health_centers: list[HealthCenter]
