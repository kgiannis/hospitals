# Attica Hospital On-Call (Εφημερίες) Tracker — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Python backend that scrapes the daily Attica hospital on-call PDF, parses it into structured JSON, and serves it through a FastAPI JSON API plus a small web test UI.

**Architecture:** A single FastAPI service. On request for today (Europe/Athens), it serves a cached `data/YYYY-MM-DD.json` if present; otherwise it scrapes the Ministry listing page for today's PDF link, downloads the PDF to a temp file, parses it with `pdfplumber`, writes the JSON, deletes the PDF, and serves it. The raw PDF is never persisted.

**Tech Stack:** Python 3.12+, uv (project-local venv), FastAPI, uvicorn, httpx, beautifulsoup4 + lxml, pdfplumber, pydantic.

**No automated tests in v1** (per spec). Each task verifies manually by running a command and observing output, then commits.

---

## File Structure

```
~/personal_repos/hospitals/
  pyproject.toml          # uv-managed
  .gitignore              # .venv/, data/*.json, __pycache__
  README.md
  hospitals/
    __init__.py
    constants.py          # source URL, Athens tz, Greek months
    models.py             # pydantic: Window, Hospital, Specialty, HealthCenter, DaySchedule
    windows.py            # parse_window_text(), is_open_at()
    fetcher.py            # listing scrape, find today's fdl, download PDF, now_athens()
    parser.py             # pdfplumber → DaySchedule
    store.py              # JSON cache + get_schedule() orchestrator
    main.py               # FastAPI app + routes + static web UI
  web/
    index.html
    app.js
    style.css
  data/                   # gitignored JSON cache (.gitkeep tracked)
  dev/
    dump_pdf.py           # dev-only: inspect pdfplumber output of a sample PDF
```

---

### Task 1: Project scaffold

**Files:**
- Create: `~/personal_repos/hospitals/pyproject.toml` (via `uv init`)
- Create: `hospitals/__init__.py`, `hospitals/constants.py`
- Create: `.gitignore`, `data/.gitkeep`

- [ ] **Step 1: Initialize uv project and add dependencies**

Run from the project root:

```bash
cd ~/personal_repos/hospitals
uv init --name hospitals --python 3.12 --no-workspace
rm -f main.py hello.py          # remove uv's sample entrypoint if created
uv add fastapi uvicorn httpx beautifulsoup4 lxml pdfplumber pydantic
mkdir -p hospitals web data dev
touch hospitals/__init__.py data/.gitkeep
git config user.name "Karavasilis Giannis"
git config user.email "giannis@numa.com"
```

- [ ] **Step 2: Write `.gitignore`**

Create `.gitignore`:

```gitignore
.venv/
__pycache__/
*.pyc
data/*.json
.DS_Store
```

- [ ] **Step 3: Write `hospitals/constants.py`**

```python
"""Static configuration: the source URL, timezone, and Greek month names."""

SOURCE_URL = (
    "https://www.moh.gov.gr/articles/citizen/efhmeries-nosokomeiwn/"
    "68-efhmeries-nosokomeiwn-attikhs"
)
ATHENS_TZ = "Europe/Athens"

# Genitive-case Greek month names as they appear in the file titles
# (e.g. "17 ΙΟΥΝΙΟΥ 2026"). Accents are stripped before matching, so the
# May spelling variant (ΜΑΙΟΥ / ΜΑΪΟΥ) does not matter.
GREEK_MONTHS = {
    1: "ΙΑΝΟΥΑΡΙΟΥ",
    2: "ΦΕΒΡΟΥΑΡΙΟΥ",
    3: "ΜΑΡΤΙΟΥ",
    4: "ΑΠΡΙΛΙΟΥ",
    5: "ΜΑΙΟΥ",
    6: "ΙΟΥΝΙΟΥ",
    7: "ΙΟΥΛΙΟΥ",
    8: "ΑΥΓΟΥΣΤΟΥ",
    9: "ΣΕΠΤΕΜΒΡΙΟΥ",
    10: "ΟΚΤΩΒΡΙΟΥ",
    11: "ΝΟΕΜΒΡΙΟΥ",
    12: "ΔΕΚΕΜΒΡΙΟΥ",
}
```

- [ ] **Step 4: Verify the environment**

Run:

```bash
uv run python -c "import fastapi, uvicorn, httpx, bs4, lxml, pdfplumber, pydantic; from hospitals.constants import GREEK_MONTHS; print('ok', GREEK_MONTHS[6])"
```

Expected output: `ok ΙΟΥΝΙΟΥ`

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "Scaffold uv project with dependencies and constants"
```

---

### Task 2: Data models

**Files:**
- Create: `hospitals/models.py`

- [ ] **Step 1: Write `hospitals/models.py`**

```python
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
```

- [ ] **Step 2: Verify models construct and serialize**

Run:

```bash
uv run python -c "
from hospitals.models import Window, Hospital, Specialty, DaySchedule
w = Window(start='14:30', end='08:00', crosses_midnight=True)
h = Hospital(name='Γ.Ν.Α. ΛΑΪΚΟ', window=w)
s = DaySchedule(date='2026-06-17', date_greek='X', source_fdl=1, fetched_at='t', specialties=[Specialty(name='Παθολογική', hospitals=[h])], health_centers=[])
print(s.model_dump_json())
"
```

Expected: a JSON line containing `"crosses_midnight":true` and `"name":"Παθολογική"`.

- [ ] **Step 3: Commit**

```bash
git add hospitals/models.py
git commit -m "Add pydantic models for the day schedule"
```

---

### Task 3: Time-window logic

**Files:**
- Create: `hospitals/windows.py`

- [ ] **Step 1: Write `hospitals/windows.py`**

```python
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
```

- [ ] **Step 2: Verify the logic against known cases**

Run:

```bash
uv run python -c "
from hospitals.windows import parse_window_text, is_open_at
night = parse_window_text('14:30 – 08:00 επομένης')
print('night', night.model_dump())
assert night.crosses_midnight is True
assert is_open_at(night, '23:00') is True
assert is_open_at(night, '07:00') is True
assert is_open_at(night, '12:00') is False
day = parse_window_text('08:00 – 14:30')
assert day.crosses_midnight is False
assert is_open_at(day, '10:00') is True
assert is_open_at(day, '20:00') is False
full = parse_window_text('08:00 – 08:00 επομένης')
assert is_open_at(full, '03:00') is True
print('all window assertions passed')
"
```

Expected output ends with: `all window assertions passed`

- [ ] **Step 3: Commit**

```bash
git add hospitals/windows.py
git commit -m "Add time-window parsing and is_open_at logic"
```

---

### Task 4: Fetcher (listing scrape + PDF download)

**Files:**
- Create: `hospitals/fetcher.py`

- [ ] **Step 1: Write `hospitals/fetcher.py`**

```python
"""Find and download today's Attica on-call PDF from the Ministry site."""

from __future__ import annotations

import re
import tempfile
import unicodedata
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from hospitals.constants import ATHENS_TZ, GREEK_MONTHS, SOURCE_URL

_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
_FDL_RE = re.compile(r"fdl=(\d+)")


def now_athens() -> datetime:
    return datetime.now(ZoneInfo(ATHENS_TZ))


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def _normalize(text: str) -> str:
    return _strip_accents(text).upper().strip()


def fetch_listing() -> str:
    """Return the HTML of the Attica listing page."""
    response = httpx.get(
        SOURCE_URL, headers={"User-Agent": _USER_AGENT}, follow_redirects=True, timeout=30
    )
    response.raise_for_status()
    return response.text


def find_today_pdf(html: str, day: datetime) -> tuple[int, str] | None:
    """Return (fdl_id, link_text) for today's PDF link, or None if not found.

    The PDF anchor text looks like "ΤΕΤΑΡΤΗ 17 ΙΟΥΝΙΟΥ 2026.pdf"; the DOC
    sibling has the same text without the ".pdf" suffix, so we require it.
    """
    target = _normalize(f"{day.day} {GREEK_MONTHS[day.month]} {day.year}")
    soup = BeautifulSoup(html, "lxml")
    for anchor in soup.find_all("a", href=_FDL_RE):
        text = anchor.get_text(strip=True)
        normalized = _normalize(text)
        if target in normalized and normalized.endswith(".PDF"):
            fdl = int(_FDL_RE.search(anchor["href"]).group(1))
            return fdl, text
    return None


def download_pdf(fdl: int) -> Path:
    """Download the PDF for ``fdl`` to a temp file and return its path."""
    url = f"{SOURCE_URL}?fdl={fdl}"
    response = httpx.get(
        url,
        headers={"User-Agent": _USER_AGENT, "Referer": SOURCE_URL},
        follow_redirects=True,
        timeout=60,
    )
    response.raise_for_status()
    handle, name = tempfile.mkstemp(suffix=".pdf")
    path = Path(name)
    path.write_bytes(response.content)
    return path
```

- [ ] **Step 2: Verify against the live site**

Run (this hits the real Ministry site):

```bash
uv run python -c "
from hospitals.fetcher import fetch_listing, find_today_pdf, download_pdf, now_athens
html = fetch_listing()
found = find_today_pdf(html, now_athens())
print('found:', found)
if found:
    p = download_pdf(found[0])
    print('downloaded', p, p.stat().st_size, 'bytes')
    print('is pdf:', p.read_bytes()[:5])
"
```

Expected: `found:` prints a tuple like `(31204, 'ΤΕΤΑΡΤΗ 17 ΙΟΥΝΙΟΥ 2026.pdf')`, the download is tens-to-hundreds of KB, and `is pdf:` prints `b'%PDF-'`.

If `found:` is `None` (today's file may not be published yet, or a date mismatch), try the most recent listed day by temporarily checking a known-present date — but for normal daytime runs it should resolve. Keep the downloaded temp path for Task 5.

- [ ] **Step 3: Commit**

```bash
git add hospitals/fetcher.py
git commit -m "Add fetcher: scrape listing and download today's PDF"
```

---

### Task 5: Parser (pdfplumber → DaySchedule)

**Files:**
- Create: `dev/dump_pdf.py` (dev-only inspection helper)
- Create: `hospitals/parser.py`

> This is the highest-risk component. The two steps below are deliberately split: first inspect the real PDF, then implement against what you actually see. Expect to iterate on the parser within this task until the printed JSON is correct.

- [ ] **Step 1: Write the inspection helper `dev/dump_pdf.py`**

```python
"""Dev helper: download today's PDF and dump pdfplumber's view of it.

Usage: uv run python dev/dump_pdf.py
Prints, per page: the raw text, and the tables pdfplumber detects with the
default (line-based) strategy. Use this to decide the parser strategy.
"""

import pdfplumber

from hospitals.fetcher import download_pdf, fetch_listing, find_today_pdf, now_athens


def main() -> None:
    found = find_today_pdf(fetch_listing(), now_athens())
    if not found:
        print("No PDF found for today")
        return
    pdf_path = download_pdf(found[0])
    print(f"PDF: {pdf_path}  (date link: {found[1]})")
    with pdfplumber.open(pdf_path) as pdf:
        for index, page in enumerate(pdf.pages):
            print(f"\n===== PAGE {index} TEXT =====")
            print(page.extract_text())
            print(f"\n===== PAGE {index} TABLES (line strategy) =====")
            for table in page.extract_tables():
                for row in table:
                    print(row)
    pdf_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Inspect the PDF**

Run:

```bash
uv run python dev/dump_pdf.py | tee /tmp/pdf_dump.txt
```

Read `/tmp/pdf_dump.txt`. Confirm two things that drive the implementation:
1. Whether `extract_tables()` returns a clean grid (the table has ruled borders) — preferred path.
2. The exact header strings of the time-window columns and the leftmost specialty column, and where the health-center lines (`Κ.Υ. …: (HH:MM – HH:MM)`) appear in the page text.

- [ ] **Step 3: Write `hospitals/parser.py`**

This implementation assumes `extract_tables()` yields a grid whose first row is the header (`["Κλινικές", "08:00 – 14:30", …, "ΠΑΡΑΤΗΡΗΣΕΙΣ"]`) and whose following rows carry a specialty label in column 0 (blank = continuation of the previous specialty) and newline-separated hospital names in the time columns. Health centers are read from the page text by regex. If Step 2 showed a different shape, adapt the column/row mapping here and re-run Step 4 until the JSON is correct.

```python
"""Parse the daily Attica on-call PDF into a DaySchedule."""

from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

from hospitals.models import DaySchedule, HealthCenter, Hospital, Specialty, Window
from hospitals.windows import parse_window_text

# Inline per-cell override, e.g. "Γ.Ν.Α ΚΑΤ έως 22:00".
_OVERRIDE_RE = re.compile(r"\s*(έως\s*\d{1,2}:\d{2}|\(\s*\d{1,2}:\d{2}\s*[–-].*?\))\s*$")
# Health-center line, e.g. "Κ.Υ. ΑΛΕΞΑΝΔΡΑΣ: (08:00 – 08:00 επομένης)".
_KY_RE = re.compile(
    r"(Κ\.?\s?Υ\.?[^:\n]+?):\s*\(?\s*(\d{1,2}:\d{2})\s*[–-]\s*(\d{1,2}:\d{2})\s*([^)\n]*)\)?"
)
_TIME_HEADER_RE = re.compile(r"\d{1,2}:\d{2}")


def _split_cell_into_hospitals(cell: str, column_window: Window) -> list[Hospital]:
    """Split a table cell (newline-separated names) into Hospital entries,
    applying any inline time override to the window and note."""
    hospitals: list[Hospital] = []
    if not cell:
        return hospitals
    for raw in cell.split("\n"):
        name = raw.strip()
        if not name:
            continue
        note: str | None = None
        window = column_window
        match = _OVERRIDE_RE.search(name)
        if match:
            note = match.group(1).strip()
            name = name[: match.start()].strip()
            override_window = parse_window_text(f"{column_window.start} {note}")
            if override_window is not None:
                window = override_window
        hospitals.append(Hospital(name=name, window=window, note=note))
    return hospitals


def _parse_health_centers(text: str) -> list[HealthCenter]:
    centers: list[HealthCenter] = []
    for match in _KY_RE.finditer(text):
        name = re.sub(r"\s+", " ", match.group(1)).strip()
        window = parse_window_text(f"{match.group(2)} – {match.group(3)} {match.group(4)}")
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
    full_text_parts: list[str] = []
    column_windows: dict[int, Window] = {}

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            full_text_parts.append(page.extract_text() or "")
            for table in page.extract_tables():
                if not table:
                    continue
                header = table[0]
                # Map each column index that holds a time range to its Window.
                for col_index, cell in enumerate(header):
                    if cell and _TIME_HEADER_RE.search(cell):
                        window = parse_window_text(cell)
                        if window is not None:
                            column_windows[col_index] = window
                # Data rows: column 0 = specialty (carry forward when blank).
                current: Specialty | None = None
                for row in table[1:]:
                    label = (row[0] or "").strip() if row else ""
                    if label:
                        current = Specialty(name=label, hospitals=[])
                        specialties.append(current)
                    if current is None:
                        continue
                    for col_index, window in column_windows.items():
                        if col_index < len(row):
                            current.hospitals.extend(
                                _split_cell_into_hospitals(row[col_index] or "", window)
                            )

    health_centers = _parse_health_centers("\n".join(full_text_parts))
    # Drop specialties that ended up with no on-duty hospital.
    specialties = [s for s in specialties if s.hospitals]
    return DaySchedule(
        date=date_str,
        date_greek=date_greek,
        source_fdl=source_fdl,
        fetched_at=fetched_at,
        specialties=specialties,
        health_centers=health_centers,
    )
```

- [ ] **Step 4: Verify the parser against today's real PDF**

Run:

```bash
uv run python -c "
from hospitals.fetcher import fetch_listing, find_today_pdf, download_pdf, now_athens
from hospitals.parser import parse_pdf
now = now_athens()
fdl, text = find_today_pdf(fetch_listing(), now)
p = download_pdf(fdl)
sched = parse_pdf(p, date_str=now.strftime('%Y-%m-%d'), date_greek=text, source_fdl=fdl, fetched_at=now.isoformat())
p.unlink(missing_ok=True)
print('specialties:', [s.name for s in sched.specialties])
print('health centers:', [c.name for c in sched.health_centers])
import json
first = sched.specialties[0]
print(first.name, '->', json.dumps([h.model_dump() for h in first.hospitals], ensure_ascii=False))
"
```

Expected: a list of specialty names (Παθολογική, Καρδιολογική, Χειρουργική, …), a non-empty health-centers list, and the first specialty's hospitals with sensible windows. Compare against `/tmp/pdf_dump.txt` and the live PDF. **Iterate on `parser.py` until the output matches the document**, then proceed.

- [ ] **Step 5: Commit**

```bash
git add hospitals/parser.py dev/dump_pdf.py
git commit -m "Add pdfplumber parser producing a DaySchedule"
```

---

### Task 6: Store + orchestrator

**Files:**
- Create: `hospitals/store.py`

- [ ] **Step 1: Write `hospitals/store.py`**

```python
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
```

- [ ] **Step 2: Verify caching and PDF cleanup**

Run:

```bash
uv run python -c "
from hospitals.store import get_schedule, DATA_DIR
import glob, os
s = get_schedule(refresh=True)
print('specialties:', len(s.specialties) if s else None)
files = glob.glob(str(DATA_DIR / '*.json'))
print('cache files:', files)
# second call must read from cache (no network) and return same date
s2 = get_schedule()
print('cached date:', s2.date)
print('leftover temp pdfs in /tmp:', glob.glob('/tmp/*.pdf')[:3])
"
```

Expected: a JSON cache file under `data/` for today, `cached date:` prints today's date. (Temp PDFs created by this run are deleted; any unrelated `/tmp/*.pdf` are not ours.)

- [ ] **Step 3: Commit**

```bash
git add hospitals/store.py
git commit -m "Add JSON cache store and get_schedule orchestrator"
```

---

### Task 7: FastAPI app + routes

**Files:**
- Create: `hospitals/main.py`

- [ ] **Step 1: Write `hospitals/main.py`**

```python
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
```

- [ ] **Step 2: Create a placeholder web dir so the mount has something to serve**

```bash
mkdir -p web && printf '<!doctype html><title>ok</title><h1>backend up</h1>' > web/index.html
```

- [ ] **Step 3: Verify the API with the server running**

Start the server in the background, hit the endpoints, then stop it:

```bash
uv run uvicorn hospitals.main:app --port 8000 &
sleep 4
echo "--- specialties ---"; curl -s localhost:8000/api/specialties | head -c 600; echo
echo "--- now ---"; curl -s localhost:8000/api/now | head -c 600; echo
echo "--- health centers ---"; curl -s localhost:8000/api/health-centers | head -c 400; echo
kill %1
```

Expected: `/api/specialties` returns today's date and a list of specialty names; `/api/now` returns groups of currently-open hospitals; `/api/health-centers` returns a list. (If today's file is unpublished, expect HTTP 503 with the "not published yet" detail — that is correct behavior.)

- [ ] **Step 4: Commit**

```bash
git add hospitals/main.py web/index.html
git commit -m "Add FastAPI routes and static web mount"
```

---

### Task 8: Web test UI

**Files:**
- Modify/replace: `web/index.html`
- Create: `web/app.js`, `web/style.css`

- [ ] **Step 1: Write `web/index.html`**

```html
<!doctype html>
<html lang="el">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Εφημερίες Νοσοκομείων Αττικής</title>
    <link rel="stylesheet" href="/style.css" />
  </head>
  <body>
    <header>
      <h1>Εφημερίες Αττικής</h1>
      <p id="date"></p>
    </header>

    <section>
      <label for="specialty">Ειδικότητα</label>
      <input id="specialty" list="specialties" placeholder="Αναζήτηση ειδικότητας…" />
      <datalist id="specialties"></datalist>
      <button id="show-health-centers" type="button">Κέντρα Υγείας</button>
    </section>

    <main id="results"></main>
    <script src="/app.js"></script>
  </body>
</html>
```

- [ ] **Step 2: Write `web/style.css`**

```css
* { box-sizing: border-box; }
body { font-family: system-ui, sans-serif; margin: 0; padding: 1rem; max-width: 720px; }
header h1 { margin: 0 0 0.25rem; font-size: 1.3rem; }
#date { color: #555; margin: 0 0 1rem; }
section { display: flex; gap: 0.5rem; flex-wrap: wrap; align-items: center; margin-bottom: 1rem; }
input { flex: 1 1 220px; padding: 0.5rem; font-size: 1rem; }
button { padding: 0.5rem 0.75rem; font-size: 1rem; cursor: pointer; }
.group { margin-bottom: 1rem; }
.group h2 { font-size: 1rem; margin: 0 0 0.25rem; }
.hospital { padding: 0.5rem; border: 1px solid #ddd; border-radius: 6px; margin-bottom: 0.4rem; cursor: pointer; }
.hospital.open { border-color: #1a7f37; background: #eaf6ec; }
.window { color: #555; font-size: 0.9rem; }
.note { color: #b35900; font-size: 0.85rem; }
.badge { font-size: 0.75rem; color: #1a7f37; font-weight: 600; }
```

- [ ] **Step 3: Write `web/app.js`**

```javascript
const results = document.getElementById("results");
const input = document.getElementById("specialty");
const datalist = document.getElementById("specialties");

function fmtWindow(w) {
  const suffix = w.crosses_midnight ? " (επομένης)" : "";
  return `${w.start} – ${w.end}${suffix}`;
}

function hospitalCard(h) {
  const card = document.createElement("div");
  card.className = "hospital" + (h.open_now ? " open" : "");
  const note = h.note ? `<div class="note">${h.note}</div>` : "";
  const badge = h.open_now ? `<span class="badge">ΑΝΟΙΧΤΟ ΤΩΡΑ</span>` : "";
  card.innerHTML =
    `<div>${h.name} ${badge}</div>` +
    `<div class="window">${fmtWindow(h.window)}</div>${note}`;
  card.addEventListener("click", () => showHospital(h.name));
  return card;
}

async function loadSpecialties() {
  const res = await fetch("/api/specialties");
  if (!res.ok) {
    results.textContent = "Το πρόγραμμα δεν είναι ακόμη διαθέσιμο.";
    return;
  }
  const data = await res.json();
  document.getElementById("date").textContent = data.date_greek;
  datalist.innerHTML = "";
  for (const name of data.specialties) {
    const opt = document.createElement("option");
    opt.value = name;
    datalist.appendChild(opt);
  }
  showNow();
}

async function showNow() {
  const res = await fetch("/api/now");
  const data = await res.json();
  results.innerHTML = `<h2>Ανοιχτά τώρα (${data.now})</h2>`;
  for (const group of data.groups) {
    const block = document.createElement("div");
    block.className = "group";
    block.innerHTML = `<h2>${group.specialty}</h2>`;
    for (const h of group.hospitals) block.appendChild(hospitalCard({ ...h, open_now: true }));
    results.appendChild(block);
  }
}

async function showSpecialty(name) {
  const res = await fetch(`/api/specialties/${encodeURIComponent(name)}`);
  if (!res.ok) return;
  const data = await res.json();
  results.innerHTML = `<h2>${data.specialty} (τώρα ${data.now})</h2>`;
  for (const h of data.hospitals) results.appendChild(hospitalCard(h));
}

async function showHospital(name) {
  const res = await fetch(`/api/hospitals/${encodeURIComponent(name)}`);
  if (!res.ok) return;
  const data = await res.json();
  results.innerHTML = `<h2>${data.hospital} (τώρα ${data.now})</h2>`;
  for (const e of data.entries) {
    const card = document.createElement("div");
    card.className = "hospital" + (e.open_now ? " open" : "");
    const note = e.note ? `<div class="note">${e.note}</div>` : "";
    card.innerHTML =
      `<div>${e.specialty}</div><div class="window">${fmtWindow(e.window)}</div>${note}`;
    results.appendChild(card);
  }
}

async function showHealthCenters() {
  const res = await fetch("/api/health-centers");
  if (!res.ok) return;
  const data = await res.json();
  results.innerHTML = `<h2>Κέντρα Υγείας (τώρα ${data.now})</h2>`;
  for (const c of data.health_centers) results.appendChild(hospitalCard(c));
}

input.addEventListener("change", () => {
  if (input.value) showSpecialty(input.value);
});
document.getElementById("show-health-centers").addEventListener("click", showHealthCenters);

loadSpecialties();
```

- [ ] **Step 4: Verify the UI in a browser**

Run:

```bash
uv run uvicorn hospitals.main:app --port 8000
```

Open <http://localhost:8000> in a browser. Confirm: today's Greek date shows in the header; the "Ανοιχτά τώρα" list renders; typing/selecting a specialty shows its hospitals with windows and green "open now" highlighting; clicking a hospital shows all its specialties/windows for the day; the "Κέντρα Υγείας" button lists the health centers. Stop with Ctrl+C.

- [ ] **Step 5: Commit**

```bash
git add web/index.html web/app.js web/style.css
git commit -m "Add web test UI for the on-call API"
```

---

### Task 9: README and final smoke test

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write `README.md`**

````markdown
# Attica Hospital On-Call Tracker

Scrapes the Greek Ministry of Health's daily Attica hospital on-call (εφημερία)
PDF, parses it into structured JSON, and serves it via a small API + web UI.

## Run

```bash
uv run uvicorn hospitals.main:app --reload
```

Then open <http://localhost:8000>.

## How it works

On the first request each day it downloads today's PDF, parses it with
`pdfplumber`, writes `data/YYYY-MM-DD.json`, and deletes the PDF. Later requests
read the cached JSON. Add `?refresh=1` to any API endpoint to force a re-fetch.

## API

- `GET /api/now` — hospitals on duty right now, grouped by specialty
- `GET /api/specialties` — specialty names
- `GET /api/specialties/{name}` — hospitals for a specialty (with `open_now`)
- `GET /api/hospitals/{name}` — all specialties/windows for one hospital today
- `GET /api/health-centers` — on-call health centers

All endpoints are for **today**, Europe/Athens. Attica region only.

## Not in v1

No database, no tests, no auth, no maps/phone, no other regions, no date picker,
no mobile app (planned as a separate phase).
````

- [ ] **Step 2: Final smoke test**

```bash
uv run uvicorn hospitals.main:app --port 8000 &
sleep 4
curl -s localhost:8000/api/specialties | head -c 300; echo
curl -s "localhost:8000/api/now?refresh=1" | head -c 300; echo
kill %1
```

Expected: both endpoints return JSON for today without errors.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "Add README and final smoke test"
```

---

## Self-Review Notes

- **Spec coverage:** open-now landing (Task 7 `/api/now`, Task 8 `showNow`), searchable specialty → hospitals + hours (Tasks 7–8), per-hospital view (Task 7 `/api/hospitals/{name}`, Task 8 `showHospital`), health centers (Tasks 7–8), today-only Europe/Athens (Tasks 4, 7), JSON cache no-DB + PDF discarded (Task 6), uv project-local venv (Task 1). All covered.
- **Inline overrides** (`έως 22:00`) handled in `parser._split_cell_into_hospitals` (Task 5) and surfaced as `note` everywhere.
- **Risk:** the parser (Task 5) depends on the real PDF's table structure; Step 2 inspects it and Step 4 iterates against live data before moving on.
- **Type consistency:** `Window`/`Hospital`/`Specialty`/`HealthCenter`/`DaySchedule` defined in Task 2 are used unchanged in Tasks 3–7; endpoint JSON keys (`open_now`, `window`, `note`, `groups`, `entries`) match between Task 7 and the Task 8 JS.
