"""Parse the daily Attica on-call PDF into a DaySchedule.

pdfplumber's line-based ``extract_tables()`` yields a clean 7-column grid for
these PDFs: column 0 is the specialty (Κλινικές), columns 1-5 are time-window
columns whose headers carry the hours, and the final ΠΑΡΑΤΗΡΗΣΕΙΣ column holds
free-text notes. The header row repeats on every page and must be skipped.

Within a time-window cell, several hospitals are stacked and pdfplumber joins
them with newlines. A single hospital's name can itself wrap across several
lines, and an inline duty-hour override ("έως 22:00", "ΕΩΣ 21:00", "08:00 έως
15:00") may sit on its own line. We therefore reassemble each cell into whole
hospital entries by treating a line as a continuation unless it begins a new
hospital name.
"""

from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

from hospitals.models import DaySchedule, HealthCenter, Hospital, Specialty, Window
from hospitals.windows import parse_window_text

# A hospital name begins either with a dotted abbreviation (Γ.Ν.Α., Π.Γ.Ν.Α.,
# Α.Ο.Ν.Α., Ν.Δ.Ν.Α., Γ.Ο.Ν.Κ., Ν.Α., Γ.Ν., ...) or with one of the bare
# all-caps names that carry no abbreviation prefix.
_BARE_NAME_STARTS = ("ΠΕΙΡΑΙΑΣ", "ΠΟΛΥΔΥΝΑΜΗ")
_ABBREV_START_RE = re.compile(r"^(?:[Α-ΩΪΫ]\.){1,}")

# Inline / trailing per-cell duty override meaning "until HH:MM". The word for
# "until" appears in several case/accent variants — "έως", "εως", "ΕΩΣ" — so we
# match each letter (epsilon, omega, final/regular sigma) against its variants.
# Captures the trailing forms "έως 23:00", "εως 16:00", "ΕΩΣ 21:00" and the
# "08:00 έως 15:00" form, plus the parenthesized variants "(έως 16:00)" and
# "(08:00 - 15:00)". A trailing qualifier word (e.g. "ΜΟΝΟ") and/or punctuation
# may follow the override; both are absorbed so no time text is left on the name.
_HHMM = r"\d{1,2}:\d{2}"
_EOS = r"[εέΕ][ωώΩ][ςσΣ]"
# Bare "<start>? έως <end>" or parenthesized "(έως <end>)" / "(<start> - <end>)".
_OVERRIDE_BODY = (
    rf"(?:(?:{_HHMM}\s*)?{_EOS}\s*{_HHMM}"
    rf"|\(\s*(?:{_EOS}\s*)?{_HHMM}(?:\s*[–\-]\s*{_HHMM})?\s*\))"
)
# An optional trailing all-caps qualifier word (e.g. "ΜΟΝΟ") may follow.
_OVERRIDE_RE = re.compile(
    rf"\s*({_OVERRIDE_BODY}(?:\s+[Α-ΩΪΫ]+)?)\s*[.,]?\s*$"
)
# Health-center line, e.g. "Κ.Υ. ΑΛΕΞΑΝΔΡΑΣ: (08:00 – 08:00 επομένης)".
_KY_RE = re.compile(
    r"(Κ\.?\s?Υ\.?[^:\n]+?):\s*\(?\s*(\d{1,2}:\d{2})\s*[–\-]\s*"
    r"(\d{1,2}:\d{2})\s*([^)\n]*)\)?"
)
_TIME_HEADER_RE = re.compile(r"\d{1,2}:\d{2}")
_HEADER_LABEL = "Κλινικές"


def _starts_new_hospital(line: str) -> bool:
    """True if ``line`` looks like the first line of a hospital entry rather
    than a continuation (a wrapped name tail or a stray override line)."""
    stripped = line.strip()
    if not stripped:
        return False
    if _ABBREV_START_RE.match(stripped):
        return True
    return any(stripped.startswith(prefix) for prefix in _BARE_NAME_STARTS)


def _group_cell_entries(cell: str) -> list[str]:
    """Group the newline-split lines of a cell into one string per hospital.

    The first line always opens an entry; subsequent lines that do not look
    like a new hospital name are appended to the current entry (they are
    wrapped name fragments or override lines such as "έως 23:00")."""
    entries: list[str] = []
    for raw in cell.split("\n"):
        line = raw.strip()
        if not line:
            continue
        if entries and not _starts_new_hospital(line):
            entries[-1] = f"{entries[-1]} {line}"
        else:
            entries.append(line)
    return entries


def _apply_override(window: Window, end_hhmm: str) -> Window:
    """Return a copy of ``window`` whose end is replaced by ``end_hhmm``.

    The override always shortens the same day's duty, so the result no longer
    crosses midnight."""
    return Window(start=window.start, end=end_hhmm, crosses_midnight=False)


def _split_cell_into_hospitals(cell: str, column_window: Window) -> list[Hospital]:
    """Turn one time-window cell into Hospital entries, applying any inline
    duty-hour override to the window and recording it as the note."""
    hospitals: list[Hospital] = []
    for entry in _group_cell_entries(cell):
        name = re.sub(r"\s+", " ", entry).strip()
        note: str | None = None
        window = column_window
        match = _OVERRIDE_RE.search(name)
        if match:
            note = re.sub(r"\s+", " ", match.group(1)).strip().rstrip(".")
            name = name[: match.start()].strip()
            override_times = _TIME_HEADER_RE.findall(note)
            if override_times:
                window = _apply_override(column_window, override_times[-1])
        if name:
            hospitals.append(Hospital(name=name, window=window, note=note))
    return hospitals


def _parse_health_centers(text: str) -> list[HealthCenter]:
    centers: list[HealthCenter] = []
    for match in _KY_RE.finditer(text):
        name = re.sub(r"\s+", " ", match.group(1)).strip()
        window = parse_window_text(
            f"{match.group(2)} – {match.group(3)} {match.group(4)}"
        )
        if window is not None:
            centers.append(HealthCenter(name=name, window=window))
    return centers


def parse_pdf(
    pdf_path: Path,
    *,
    date_str: str,
    date_greek: str,
    source_fdl: int,
    fetched_at: str,
) -> DaySchedule:
    specialties: list[Specialty] = []
    by_name: dict[str, Specialty] = {}
    full_text_parts: list[str] = []
    column_windows: dict[int, Window] = {}

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            full_text_parts.append(page.extract_text() or "")
            for table in page.extract_tables():
                if not table:
                    continue
                for row in table:
                    if not row:
                        continue
                    label = (row[0] or "").strip()
                    # The header row repeats on every page; use it to learn the
                    # time-window columns and never treat it as a specialty.
                    if label == _HEADER_LABEL:
                        for col_index, cell in enumerate(row):
                            if cell and _TIME_HEADER_RE.search(cell):
                                window = parse_window_text(cell)
                                if window is not None:
                                    column_windows[col_index] = window
                        continue
                    if not label:
                        continue
                    label = re.sub(r"\s+", " ", label).strip()
                    specialty = by_name.get(label)
                    if specialty is None:
                        specialty = Specialty(name=label, hospitals=[])
                        by_name[label] = specialty
                        specialties.append(specialty)
                    for col_index, window in column_windows.items():
                        if col_index < len(row):
                            specialty.hospitals.extend(
                                _split_cell_into_hospitals(row[col_index] or "", window)
                            )

    health_centers = _parse_health_centers("\n".join(full_text_parts))
    specialties = [s for s in specialties if s.hospitals]
    return DaySchedule(
        date=date_str,
        date_greek=date_greek,
        source_fdl=source_fdl,
        fetched_at=fetched_at,
        specialties=specialties,
        health_centers=health_centers,
    )
