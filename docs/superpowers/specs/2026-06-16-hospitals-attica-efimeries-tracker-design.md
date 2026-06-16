# Attica Hospital On-Call (Εφημερίες) Tracker — Design

**Date:** 2026-06-16
**Status:** Approved, pre-implementation
**Author:** Giannis (with Claude)

## Purpose

The Greek Ministry of Health publishes daily hospital on-call (εφημερία) schedules
for Attica as PDF/DOC files only — no API. Reading those files in an emergency is
slow. This project scrapes the daily PDF, extracts the schedule into structured
data, and serves it through a small API so a user can, in seconds:

1. Open the app and see which hospitals are on duty **right now**.
2. Pick a **specialty** (searchable) and see which hospitals cover it, with their hours.
3. Tap a hospital and see **every specialty/window it is on duty for** that day
   (a full per-hospital view).
4. See the on-call **health centers** (Κέντρα Υγείας) for the day.

Single user (the author) for v1. Personal project.

## Source

- Listing page (Attica only):
  `https://www.moh.gov.gr/articles/citizen/efhmeries-nosokomeiwn/68-efhmeries-nosokomeiwn-attikhs`
- One file pair per day. Download links are **article-relative**: `?fdl=<id>`
  (e.g. `…/68-efhmeries-nosokomeiwn-attikhs?fdl=31204`). The PDF and DOC of a day are
  adjacent ids (PDF first in observed data).
- The "DOC" is a **legacy binary `.doc`** (OLE, Greek code page 1253) — `python-docx`
  cannot read it. We use the **PDF**.

## Document structure (what we extract)

The core of each daily PDF is a 2-D table:

- **Rows = specialties** (Κλινικές): Παθολογική, Καρδιολογική, Χειρουργική,
  Αγγειοχειρουργική, …
- **Columns = time windows**: `08:00–14:30`, `08:00–16:00`, `08:00–23:00`,
  `14:30–08:00 επομένης`, `08:00–08:00 επομένης`, plus a ΠΑΡΑΤΗΡΗΣΕΙΣ (notes) column.
- **Cells = hospital names** (e.g. `Γ.Ν.Α. «ΛΑΪΚΟ»`).

A hospital's hours = the **column header**, but individual cells can carry an **inline
override** (e.g. `Γ.Ν.Α ΚΑΤ έως 22:00` in the night column → on duty only until 22:00).
These overrides must be captured, or we would direct someone to a closed hospital.

Also present:
- The date header (`ΤΕΤΑΡΤΗ 17 ΙΟΥΝΙΟΥ 2026`).
- On-call health centers (Εφημερεύοντα Κέντρα Υγείας): a **flat list with explicit
  hours**, no specialty breakdown (primary/general care, not specialized emergencies).

## Architecture

A single Python service (**FastAPI + uvicorn**) serving both the JSON API and a static
web test UI.

```
request (date = today, Europe/Athens)
   │
   ├─ data/YYYY-MM-DD.json exists?  ── yes ──▶ load & serve
   │                                  no
   ├─ fetcher: scrape listing page → find today's ?fdl= → download PDF to temp file
   ├─ parser: pdfplumber → structured schedule
   ├─ store:  write data/YYYY-MM-DD.json, delete temp PDF
   └─ serve
```

The raw PDF exists only as a temp file during parsing and is deleted immediately.
JSON is the only persisted artifact (requirement: no database). A `?refresh=1` query
param forces a re-fetch (used while tuning the parser).

## Data model — `data/YYYY-MM-DD.json`

```json
{
  "date": "2026-06-17",
  "date_greek": "ΤΕΤΑΡΤΗ 17 ΙΟΥΝΙΟΥ 2026",
  "source_fdl": 31204,
  "fetched_at": "2026-06-17T06:30:00+03:00",
  "specialties": [
    {
      "name": "Παθολογική",
      "hospitals": [
        {"name": "Γ.Ν.Α. «ΛΑΪΚΟ»",
         "window": {"start": "14:30", "end": "08:00", "crosses_midnight": true},
         "note": null},
        {"name": "Γ.Ν.Α ΚΑΤ",
         "window": {"start": "14:30", "end": "22:00", "crosses_midnight": false},
         "note": "έως 22:00"}
      ]
    }
  ],
  "health_centers": [
    {"name": "Κ.Υ. ΑΛΕΞΑΝΔΡΑΣ",
     "window": {"start": "08:00", "end": "08:00", "crosses_midnight": true}}
  ]
}
```

- `window` derives from the column header. An inline override replaces the end time and
  is preserved verbatim in `note`.
- `crosses_midnight` makes the "open now" comparison correct for night windows
  (start > end means the window spans midnight).

## Parser plan (`parser.py`)

The riskiest component. Fixed-layout parsing is iterative; expect tuning against several
days' files. During development, keep the raw extracted text available for debugging.

1. Read the **column header row** (time-window strings) → column x-boundaries.
2. Read the **leftmost column** (specialty labels) → row y-boundaries.
3. Use pdfplumber **explicit-lines table extraction** with those boundaries → a grid;
   each cell holds zero or more hospital names (split on line breaks / blanks).
4. Regex-detect inline overrides (`έως HH:MM`, `(HH:MM-HH:MM)`) → split into `note` +
   adjusted window.
5. Parse the **health-centers block** separately by regex
   (`Κ.Υ. <name>: (HH:MM – HH:MM)`).

## Time-window logic (`windows.py`)

- A window is `{start: "HH:MM", end: "HH:MM", crosses_midnight: bool}`.
- `is_open_at(window, now)` handles midnight crossing: if `crosses_midnight`, open when
  `now >= start OR now <= end`; otherwise open when `start <= now <= end`.
- "now" is always real current time in **Europe/Athens**.

## API (all implicitly today, Europe/Athens)

- `GET /api/now` — everything on duty right now, grouped by specialty (landing view).
- `GET /api/specialties` — list of specialty names (dropdown source).
- `GET /api/specialties/{name}` — hospitals for that specialty, each with `window` +
  `open_now`.
- `GET /api/hospitals/{name}` — every specialty + `window` + `open_now` that this
  hospital is on duty for today (per-hospital view; derived by scanning all specialties
  in the day's parsed schedule).
- `GET /api/health-centers` — list with `open_now`.
- `GET /` — the web test UI.

## Web test UI (`web/`)

One static `index.html` + vanilla JS (no build step). Shows today's date, an
"Ανοιχτά τώρα" default list, a searchable specialty picker (`<input>` + `<datalist>`)
that renders hospitals with their windows and highlights open-now. Tapping a hospital
opens its full per-hospital view (all specialties/windows it covers today, via
`/api/hospitals/{name}`). A "Κέντρα Υγείας" toggle shows the health centers.
Functional only — it exists to exercise the API.

## Project layout

```
~/personal_repos/hospitals/
  pyproject.toml          # uv-managed (uv init / uv add / uv run)
  .gitignore              # .venv/, data/*.json
  README.md
  hospitals/
    main.py               # FastAPI app + routes
    fetcher.py            # listing scrape + PDF download
    parser.py             # pdfplumber → schedule
    windows.py            # Greek window parsing + is_open_at(now)
    store.py              # JSON cache read/write
    models.py             # pydantic models
    constants.py          # Greek months, source URL, column defs
  web/                    # index.html, app.js, style.css
  data/                   # gitignored JSON cache
```

Dependencies: `fastapi`, `uvicorn`, `pdfplumber`, `httpx`, `pydantic`.
Run: `uv run uvicorn hospitals.main:app --reload`.

## Tooling

- **uv** manages the project. A project-local `.venv/` is created automatically; nothing
  is installed into global Python. `.venv/` is gitignored.

## Edge cases

- **Today's file not yet published** (early morning): API returns a clear "not available
  yet" response rather than erroring.
- **Parser variance across days**: tuned iteratively; `?refresh=1` re-fetches.
- **Empty specialty cells**: a specialty with no on-duty hospital for the day → empty list.

## Non-goals (v1)

No database, no tests, no auth/rate-limiting, no geo/directions/phone, no regions other
than Attica, no date picker (today only), no mobile app.

## Phase 2 (separate spec, after backend works)

React Native / Expo mobile app consuming this API, packaged as an `.apk` for Android.
