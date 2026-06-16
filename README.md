# Attica Hospital On-Call Tracker

Scrapes the Greek Ministry of Health's daily Attica hospital on-call (εφημερία)
PDF, parses it into structured JSON, and serves it via a small API + web UI.

## Run

```bash
uv run python -m hospitals.main
```

Then open <http://localhost:9999>.

(This serves on port 9999 with auto-reload. To pick a different port, run
`uv run uvicorn hospitals.main:app --reload --port <PORT>` instead.)

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
