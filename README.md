# Attica Hospital On-Call Tracker

Scrapes the Greek Ministry of Health's daily Attica hospital on-call (εφημερία)
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

## Daily data pipeline (Phase 2A)

A scheduled GitHub Action (`.github/workflows/daily.yml`) runs
`scripts/generate_schedule.py` twice each morning (Athens time). It scrapes the
Ministry PDF for **today plus the next 7 days** (whatever is already published),
writes each day to `daily_schedules/attica/<YYYY-MM-DD>.json`, updates
`daily_schedules/attica/index.json`, and commits the changes. The downloaded
PDFs are never committed — only the parsed JSON.

These files are served for free over GitHub's raw CDN, e.g.:

```
https://raw.githubusercontent.com/kgiannis/hospitals/main/daily_schedules/attica/<YYYY-MM-DD>.json
https://raw.githubusercontent.com/kgiannis/hospitals/main/daily_schedules/attica/index.json
```

The files use the same schedule schema as the API. "Open now" is **not** stored
in them — a client computes it against the current Europe/Athens time. To
regenerate locally: `uv run python scripts/generate_schedule.py`.

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
