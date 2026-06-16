# Phase 2A — Static Data Pipeline (GitHub Actions) — Design

**Date:** 2026-06-16
**Status:** Approved, pre-implementation
**Author:** Giannis (with Claude)

## Purpose

Phase 1 built a FastAPI service that scrapes the daily Attica on-call PDF and
serves it as JSON. For distribution to a mobile app, a running server is
unnecessary: the data changes only once per day and is identical for every user.

This sub-project replaces the *deployed server* with a **static data pipeline**:
a scheduled GitHub Action runs the existing scraper/parser and commits the
day's schedule as JSON files into a public repo, which GitHub serves over its
raw-file CDN for free. The mobile app (a later sub-project) fetches those files
directly — no backend to host, no CORS, no per-user cost.

This is **sub-project A** of Phase 2. The mobile app is sub-project B, designed
and built separately, after this pipeline produces data.

## What changes vs. Phase 1

- **Generating the data** (running fetcher + parser) → moves to **GitHub Actions**.
- **Serving the data** → moves to **GitHub raw-file hosting** (CDN).
- The reusable core — `hospitals/fetcher.py`, `parser.py`, `windows.py`,
  `models.py` — is **unchanged and reused** by the new generator.
- `hospitals/main.py` and `web/` remain as a **local-development convenience**
  only; they are not deployed.
- The repository becomes **public** (it contains only a public-data scraper —
  nothing sensitive).

## Architecture

```
GitHub Actions (scheduled, runs in GitHub's cloud)
  → scripts/generate_schedule.py  (reuses hospitals.fetcher + hospitals.parser)
  → writes daily_schedules/attica/<YYYY-MM-DD>.json  (+ index.json)
  → commits & pushes if anything changed
        │
        ▼  raw.githubusercontent.com CDN  (free, HTTPS)
  Mobile app fetches today's file  (sub-project B)
```

## Repository layout

```
hospitals/                       # public repo
├── hospitals/                   # UNCHANGED reusable core
│   ├── fetcher.py  parser.py  windows.py  models.py
│   ├── store.py                 # Phase-1 cache (local dev only)
│   └── main.py                  # FastAPI app (local dev only, not deployed)
├── web/                         # Phase-1 web UI (local dev only)
├── scripts/
│   └── generate_schedule.py     # NEW
├── daily_schedules/
│   └── attica/
│       ├── 2026-06-16.json      # one per day; Phase-1 schedule schema
│       ├── 2026-06-17.json
│       └── index.json           # manifest
└── .github/workflows/
    └── daily.yml                # NEW
```

Data is namespaced by region (`attica/`) from the start so adding other Greek
regions later is additive (more folders + more parsing), not a refactor.

## Generator script — `scripts/generate_schedule.py`

Responsibilities:

1. For each date in **[today, today + 7 days]** (Europe/Athens), check whether
   the Ministry listing has a published PDF for that date (reusing
   `fetcher.find_today_pdf`, which already matches a given date). The 7-day
   look-ahead builds a buffer so a missed run or a late publish still leaves the
   app with data.
2. For each published date: download the PDF, parse it with `parser.parse_pdf`,
   and write `daily_schedules/attica/<date>.json` (the existing `DaySchedule`
   JSON schema). The downloaded PDF is deleted after parsing (never committed).
3. Write `daily_schedules/attica/index.json`:
   `{"region": "attica", "dates": ["2026-06-16", ...], "updated_at": "<ISO>"}`
   listing every date file present in the folder.
4. **Per-day error isolation:** a failure parsing one *future* day is logged and
   skipped; the run still writes the days that succeeded. But if **today's** file
   fails to generate, the script exits non-zero so the workflow is marked failed
   (and GitHub emails the owner). This protects the safety-critical "today"
   while staying resilient on buffer days.

The script reuses Phase-1 modules without modification. It writes only into
`daily_schedules/`; it does not touch the Phase-1 `data/` cache.

## GitHub Actions workflow — `.github/workflows/daily.yml`

- **Triggers:** two `schedule` crons covering mid-morning Athens across DST
  (≈08:00 and ≈11:00 local; expressed in UTC), plus `workflow_dispatch` for a
  manual run. Running twice lets a late publish or a transient failure self-heal
  the same day.
- **Permissions:** `contents: write` (uses the built-in `GITHUB_TOKEN`).
- **Concurrency:** a guard prevents overlapping runs.
- **Steps:** checkout → set up uv (`astral-sh/setup-uv`) → `uv sync` → run
  `uv run python scripts/generate_schedule.py` → `git add daily_schedules/` →
  commit **only if there are changes** (as the `github-actions[bot]` author) →
  push.
- **Failure visibility:** GitHub's default failed-run email notifies the owner
  (triggered by the non-zero "today failed" exit, or any step error). No extra
  setup.

## Output contract (what the app will consume)

- Per-day files:
  `https://raw.githubusercontent.com/<owner>/hospitals/main/daily_schedules/attica/<YYYY-MM-DD>.json`
- Manifest:
  `https://raw.githubusercontent.com/<owner>/hospitals/main/daily_schedules/attica/index.json`
- Files use the **Phase-1 `DaySchedule` schema** unchanged (date, date_greek,
  source_fdl, fetched_at, specialties[→hospitals→window/note], health_centers).
- **"Open now" is NOT in the files** — it is computed by the client against the
  current Europe/Athens time, so the files are pure, time-independent data.
- Served via GitHub's raw CDN (HTTPS, ~5-minute cache — acceptable for
  once-daily data).
- **Retention:** all day files are kept (a free historical archive). The app
  only ever requests the current date.

## Repository visibility

The repo is made **public** so the raw-file URLs are reachable without a token.
The code is a scraper over public government data; nothing sensitive is stored.
A prominent disclaimer (unofficial app; verify with the official source) will be
added with the mobile app sub-project.

## Non-goals (this sub-project)

- No mobile app (sub-project B).
- No regions beyond Attica (the layout is ready for them).
- No Google Play submission.
- FastAPI is not deployed (kept local-dev only).
- No automated tests (consistent with Phase 1; verification is running the
  generator and inspecting the committed JSON + a real Actions run).

## Verification

- Run `uv run python scripts/generate_schedule.py` locally; confirm it writes
  today's file (and any published look-ahead days) plus a correct `index.json`,
  and leaves no temp PDF behind.
- Trigger the workflow via `workflow_dispatch`; confirm it commits the files and
  that the raw URL serves the JSON.
- Confirm a simulated "today failed" path exits non-zero (workflow goes red).
