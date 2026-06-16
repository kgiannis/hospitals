"""Find and download today's Attica on-call PDF from the Ministry site."""

from __future__ import annotations

import os
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
        if target in normalized and ".PDF" in normalized:
            match = _FDL_RE.search(anchor["href"])
            if match is None:
                continue
            fdl = int(match.group(1))
            clean_label = re.split(r"\.pdf", text, flags=re.IGNORECASE)[0].strip()
            return fdl, clean_label
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
    os.close(handle)
    path = Path(name)
    path.write_bytes(response.content)
    return path
