# Attica Hospital On-Call Tracker

Greek hospitals publish their daily on-call (εφημερία) schedule for the Attica
region only as PDF/DOC files. This project reads that PDF, parses it into
structured JSON, and publishes it daily as static files that any client (such as
a mobile app) can read directly — no server to host.

## Data

The schedules are published as static JSON over GitHub's raw CDN — today plus
any of the next few days the Ministry has already released:

```
https://raw.githubusercontent.com/kgiannis/hospitals/main/daily_schedules/attica/<YYYY-MM-DD>.json
https://raw.githubusercontent.com/kgiannis/hospitals/main/daily_schedules/attica/index.json
```

A client fetches the file for the current date (`index.json` lists which dates
are available). Each hospital's `window` is its on-duty period; `note` carries
any inline override (e.g. open only until 23:00). "Open now" is computed by the
client against the current Europe/Athens time — the files carry only the
schedule.

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

The data refreshes automatically each morning via a scheduled GitHub Action
(`.github/workflows/daily.yml`); the source PDFs are never stored, only the
parsed JSON.

## Running locally (optional)

You only need this to regenerate the data yourself or to work on the parser —
consuming the published files above requires no setup.

Requirements: [uv](https://docs.astral.sh/uv/)
(`curl -LsSf https://astral.sh/uv/install.sh | sh`). uv provisions Python 3.12
and all dependencies into a project-local `.venv`; nothing touches your global
Python.

```bash
git clone https://github.com/kgiannis/hospitals.git
cd hospitals
uv sync
```

Regenerate the schedules into `daily_schedules/attica/`:

```bash
uv run python scripts/generate_schedule.py
```

### Optional API + web UI

A small FastAPI app can serve the same data over HTTP with a simple web UI —
handy for inspecting the parser output during development:

```bash
./run.sh        # serves http://localhost:9999 with auto-reload
```

On the first request each day it reads today's PDF, caches
`data/YYYY-MM-DD.json`, and serves these endpoints (append `?refresh=1` to force
a re-fetch):

- `GET /api/now` — hospitals on duty right now, grouped by specialty
- `GET /api/specialties` — specialty names
- `GET /api/specialties/{name}` — hospitals for a specialty (with `open_now`)
- `GET /api/hospitals/{name}` — all specialties/windows for one hospital today
- `GET /api/health-centers` — on-call health centers

All endpoints are for **today**, Europe/Athens. Attica region only.

## Not in v1

No database, no tests, no auth, no maps/phone, no other regions, no date picker,
no mobile app (planned as a separate phase).
