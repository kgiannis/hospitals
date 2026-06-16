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
