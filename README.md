# Attica Hospital On-Call Tracker

Reads the Greek Ministry of Health's daily Attica hospital on-call (εφημερία)
PDF, parses it into structured JSON, and serves it via a small API + web UI.

## Requirements

- [uv](https://docs.astral.sh/uv/) (the Python package/project manager).
  Install on macOS/Linux with: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- That's it — uv provisions the right Python (3.12) and all dependencies into a
  project-local `.venv`. Nothing is installed into your global Python.

## Install

```bash
git clone <repo-url> hospitals
cd hospitals
uv sync          # creates .venv and installs the locked dependencies
```

`uv sync` reads `pyproject.toml` / `uv.lock` and sets up an isolated `.venv` in
the project directory. Re-run it any time after pulling new changes.

## Run

```bash
./run.sh
```

Then open <http://localhost:9999>.

`run.sh` starts the server on port 9999 with auto-reload (it just runs
`uv run uvicorn hospitals.main:app --reload --port 9999`). To use a different
port, run that command directly with `--port <PORT>`. `uv run` activates the
project `.venv` automatically, so you never need to activate anything yourself.

## How it works

On the first request each day it downloads today's PDF, parses it with
`pdfplumber`, writes `data/YYYY-MM-DD.json`, and deletes the PDF. Later requests
read the cached JSON. Add `?refresh=1` to any API endpoint to force a re-fetch.

## Data

The daily schedules are published as static JSON files (today plus any of the
next few days already released by the Ministry):

```
https://raw.githubusercontent.com/kgiannis/hospitals/main/daily_schedules/attica/<YYYY-MM-DD>.json
https://raw.githubusercontent.com/kgiannis/hospitals/main/daily_schedules/attica/index.json
```

A client fetches the file for the current date. Each hospital's `window` is its
on-duty period; `note` carries any inline override (e.g. open only until 23:00).
"Open now" is computed by the client against the current Europe/Athens time —
the files carry only the schedule.

Example payload (trimmed):

```json
{
  "date": "2026-06-16",
  "date_greek": "ΤΡΙΤΗ 16 ΙΟΥΝΙΟΥ 2026",
  "specialties": [
    {
      "name": "Παθολογική",
      "hospitals": [
        {
          "name": "Γ.Ν.Α. «ΕΛΠΙΣ»",
          "window": { "start": "08:00", "end": "14:30", "crosses_midnight": false },
          "note": null
        },
        {
          "name": "Γ.Ν.Α. «ΠΑΜΜΑΚΑΡΙΣΤΟ»",
          "window": { "start": "08:00", "end": "23:00", "crosses_midnight": false },
          "note": "έως 23:00"
        }
      ]
    }
  ],
  "health_centers": [
    {
      "name": "Κ.Υ. ΑΛΕΞΑΝΔΡΑΣ",
      "window": { "start": "08:00", "end": "08:00", "crosses_midnight": true }
    }
  ]
}
```

The data refreshes automatically each morning (see `.github/workflows/daily.yml`).

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
