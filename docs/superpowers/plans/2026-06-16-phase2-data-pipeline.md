# Phase 2A — Static Data Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the deployed FastAPI server with a scheduled GitHub Action that scrapes the daily Attica on-call PDF, writes the schedule as static JSON into `daily_schedules/attica/`, and commits it to a public repo served over GitHub's raw CDN.

**Architecture:** A new `scripts/generate_schedule.py` reuses the unchanged Phase-1 `fetcher`/`parser` to write today + a 7-day look-ahead of `<date>.json` files plus an `index.json`. A `.github/workflows/daily.yml` runs it twice each Athens morning, commits only on change, and marks the run failed if today's file is missing. The repo is made public so the files are reachable at raw URLs.

**Tech Stack:** Python 3.12, uv, the existing `hospitals` package, GitHub Actions, `gh` CLI.

**No automated tests** (consistent with Phase 1). Each task verifies by running the generator / workflow and inspecting output, then commits.

---

## File Structure

```
hospitals/                       # existing reusable core — UNCHANGED
scripts/
  generate_schedule.py           # NEW — produces the static JSON
daily_schedules/attica/          # NEW — committed output (today + look-ahead + index.json)
.github/workflows/daily.yml      # NEW — scheduled generator
README.md                        # MODIFY — document the pipeline
```

---

### Task 1: Generator script

**Files:**
- Create: `scripts/generate_schedule.py`

- [ ] **Step 1: Write `scripts/generate_schedule.py`**

```python
"""Generate static daily on-call schedules into daily_schedules/<region>/.

Reuses the Phase-1 fetcher + parser. Designed to run in CI (GitHub Actions) on a
daily schedule, but also runnable locally. Writes today plus a look-ahead window
so a missed run or a late publish still leaves data available.

Exit code: 0 if today's schedule was written; 1 if today could not be generated
(so a CI run is marked failed and the owner is notified). Look-ahead days that
fail are logged and skipped without failing the run.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

from hospitals.fetcher import download_pdf, fetch_listing, find_today_pdf, now_athens
from hospitals.parser import parse_pdf

REGION = "attica"
LOOKAHEAD_DAYS = 7
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "daily_schedules" / REGION


def _write_index(now: datetime) -> None:
    """Write index.json listing every date file present in OUTPUT_DIR."""
    dates = sorted(p.stem for p in OUTPUT_DIR.glob("*.json") if p.name != "index.json")
    index = {"region": REGION, "dates": dates, "updated_at": now.isoformat()}
    (OUTPUT_DIR / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def generate() -> int:
    now = now_athens()
    html = fetch_listing()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    today_str = now.strftime("%Y-%m-%d")
    today_ok = False

    for offset in range(LOOKAHEAD_DAYS + 1):
        day = now + timedelta(days=offset)
        date_str = day.strftime("%Y-%m-%d")

        found = find_today_pdf(html, day)
        if found is None:
            if offset == 0:
                print(f"[WARN] No PDF published yet for today ({date_str})")
            continue

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
        except Exception as exc:  # noqa: BLE001 — per-day resilience; logged below
            print(f"[ERROR] Failed to parse {date_str}: {exc}")
            continue
        finally:
            pdf_path.unlink(missing_ok=True)

        out_path = OUTPUT_DIR / f"{date_str}.json"
        out_path.write_text(schedule.model_dump_json(indent=2), encoding="utf-8")
        print(f"[OK] Wrote {out_path.name}")
        if offset == 0:
            today_ok = True

    _write_index(now)

    if not today_ok:
        print(f"[FAIL] Today's schedule ({today_str}) was not generated")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(generate())
```

- [ ] **Step 2: Run the generator locally**

```bash
cd ~/personal_repos/hospitals
uv run python scripts/generate_schedule.py
echo "exit code: $?"
ls -1 daily_schedules/attica/
echo "--- index.json ---"; cat daily_schedules/attica/index.json
```

Expected: prints `[OK] Wrote 2026-06-16.json` (today) and possibly look-ahead days; exit code `0`; `daily_schedules/attica/` contains at least today's file plus `index.json`; `index.json` has `region`, a sorted `dates` list including today, and an `updated_at`. Confirm no `.pdf` files are left anywhere under the repo (`find . -name '*.pdf'` returns nothing).

- [ ] **Step 3: Sanity-check a generated file matches the schema**

```bash
cd ~/personal_repos/hospitals
uv run python -c "
from hospitals.models import DaySchedule
import glob
f = sorted(glob.glob('daily_schedules/attica/2*.json'))[0]
s = DaySchedule.model_validate_json(open(f, encoding='utf-8').read())
print('date', s.date, 'specialties', len(s.specialties), 'health_centers', len(s.health_centers))
"
```

Expected: loads cleanly via the Phase-1 model and prints today's date with non-zero specialty and health-center counts.

- [ ] **Step 4: Commit**

```bash
cd ~/personal_repos/hospitals
git add scripts/generate_schedule.py daily_schedules/
git commit -m "Add static schedule generator script"
```

---

### Task 2: GitHub Actions workflow

**Files:**
- Create: `.github/workflows/daily.yml`

- [ ] **Step 1: Write `.github/workflows/daily.yml`**

```yaml
name: Generate daily schedules

on:
  schedule:
    # Athens is UTC+2 (winter) / UTC+3 (summer). These two UTC times land
    # mid-morning Athens year-round, giving a same-day retry.
    - cron: "0 6 * * *"
    - cron: "0 9 * * *"
  workflow_dispatch: {}

permissions:
  contents: write

concurrency:
  group: daily-schedules
  cancel-in-progress: false

jobs:
  generate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true

      - name: Generate schedules
        id: gen
        run: |
          set +e
          uv run python scripts/generate_schedule.py
          echo "exit_code=$?" >> "$GITHUB_OUTPUT"
          exit 0

      - name: Commit and push changes
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add daily_schedules/
          if git diff --staged --quiet; then
            echo "No changes to commit"
          else
            git commit -m "Update daily schedules ($(date -u +%Y-%m-%d))"
            git push
          fi

      - name: Fail run if today's schedule is missing
        if: steps.gen.outputs.exit_code != '0'
        run: |
          echo "Today's schedule was not generated (see generator log above)."
          exit 1
```

Note on design: the generator step always exits 0 itself and records the real exit code as an output, so the **commit step still runs** and persists any look-ahead days that succeeded even when today failed. The final step then fails the run (turning it red and triggering GitHub's failure email) only when today is missing.

- [ ] **Step 2: Validate the workflow YAML locally**

```bash
cd ~/personal_repos/hospitals
uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/daily.yml')); print('YAML OK')"
```

Expected: prints `YAML OK` (no parse error). `yaml` is available via pdfplumber's dependency tree; if it is not importable, instead run `python -c "import json,sys; print('skip')"` and visually confirm indentation. (Full execution is verified after the repo is pushed, in Task 4.)

- [ ] **Step 3: Commit**

```bash
cd ~/personal_repos/hospitals
git add .github/workflows/daily.yml
git commit -m "Add daily GitHub Actions workflow to generate schedules"
```

---

### Task 3: Document the pipeline in the README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a "Daily data pipeline" section to `README.md`**

Insert the following section immediately after the "How it works" section (keep all existing content):

````markdown
## Daily data pipeline (Phase 2A)

A scheduled GitHub Action (`.github/workflows/daily.yml`) runs
`scripts/generate_schedule.py` twice each morning (Athens time). It scrapes the
Ministry PDF for **today plus the next 7 days** (whatever is already published),
writes each day to `daily_schedules/attica/<YYYY-MM-DD>.json`, updates
`daily_schedules/attica/index.json`, and commits the changes. The downloaded
PDFs are never committed — only the parsed JSON.

These files are served for free over GitHub's raw CDN, e.g.:

```
https://raw.githubusercontent.com/<owner>/hospitals/main/daily_schedules/attica/<YYYY-MM-DD>.json
https://raw.githubusercontent.com/<owner>/hospitals/main/daily_schedules/attica/index.json
```

The files use the same schedule schema as the API. "Open now" is **not** stored
in them — a client computes it against the current Europe/Athens time. To
regenerate locally: `uv run python scripts/generate_schedule.py`.
````

- [ ] **Step 2: Commit**

```bash
cd ~/personal_repos/hospitals
git add README.md
git commit -m "Document the daily data pipeline in the README"
```

---

### Task 4: Publish to GitHub and verify the live pipeline

> ⚠️ **Outward-facing — get explicit user confirmation before running Step 1.** This
> creates a PUBLIC GitHub repository under the user's account and pushes all code
> publicly. Do not run it until the user confirms the account/repo name and that
> public is intended.

**Files:** none (publishing + verification only).

- [ ] **Step 1: Create the public repo and push**

Confirm the GitHub account and repo name with the user first. Then, from the project root:

```bash
cd ~/personal_repos/hospitals
gh auth status            # confirm logged in as the intended account
gh repo create hospitals --public --source=. --remote=origin --push
```

Expected: the repo is created public and `main` is pushed. Capture the resulting
`https://github.com/<owner>/hospitals` URL — `<owner>` is the value used in the
README/raw URLs.

- [ ] **Step 2: Trigger the workflow manually and watch it**

```bash
cd ~/personal_repos/hospitals
gh workflow run daily.yml
sleep 10
gh run list --workflow=daily.yml --limit 1
# then watch the most recent run to completion:
gh run watch "$(gh run list --workflow=daily.yml --limit 1 --json databaseId --jq '.[0].databaseId')"
```

Expected: the run completes green. If it committed new/changed files, `git pull`
locally to sync them.

- [ ] **Step 3: Confirm the raw URL serves the JSON**

Replace `<owner>` with the value from Step 1:

```bash
curl -s "https://raw.githubusercontent.com/<owner>/hospitals/main/daily_schedules/attica/index.json"
```

Expected: returns the `index.json` content (region, dates, updated_at) over HTTPS.

- [ ] **Step 4: Update the README placeholder with the real owner**

Replace `<owner>` in the README's raw URLs with the actual GitHub account, then:

```bash
cd ~/personal_repos/hospitals
git add README.md
git commit -m "Use real owner in README data URLs"
git push
```

Expected: README shows the working raw URLs. Pipeline is live.

---

## Self-Review Notes

- **Spec coverage:** generator reusing fetcher/parser (Task 1), 7-day look-ahead + per-day error isolation + today-fails→exit 1 (Task 1 `generate`), `index.json` manifest (Task 1 `_write_index`), region namespacing `attica/` (Task 1 `OUTPUT_DIR`), PDF deleted not committed (Task 1 `finally` + Step 2 check), workflow twice-daily + workflow_dispatch + commit-only-on-change + commit-then-fail-on-missing-today (Task 2), raw-URL output contract + retention of all files (Tasks 1–3), repo made public + pushed (Task 4), README documentation (Tasks 3–4). FastAPI left untouched/undeployed — no task modifies it, as intended.
- **Placeholder scan:** `<owner>` in README/URLs is an intentional template resolved in Task 4 Step 4 against the real account; not a plan gap.
- **Type/name consistency:** `generate()`/`_write_index()`/`OUTPUT_DIR`/`REGION`/`LOOKAHEAD_DAYS` used consistently; `find_today_pdf(html, day) -> (fdl, date_greek)|None`, `download_pdf(fdl)`, `parse_pdf(..., date_str, date_greek, source_fdl, fetched_at)`, and `now_athens()` match the Phase-1 signatures already in the repo; output JSON via `DaySchedule.model_dump_json` matches the schema loaded in Task 1 Step 3.
- **Risk:** Task 4 is outward-facing (public repo). It is gated on explicit user confirmation and is the only task that publishes.
