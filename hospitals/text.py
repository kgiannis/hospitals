"""Greek text normalisation shared by the fetcher and the parser.

Both have to compare Greek strings that the Ministry spells inconsistently: the
listing page's file labels vary in accent (ΜΑΙΟΥ / ΜΑΪΟΥ) and the PDF's repeated
header cell varies in case (Κλινικές / ΚΛΙΝΙΚΕΣ). Folding case and accents in one
place keeps the two comparisons using the same rule.
"""

from __future__ import annotations

import unicodedata


def strip_accents(text: str) -> str:
    """Drop combining marks, so "ΜΑΪΟΥ" and "ΜΑΙΟΥ" compare equal."""
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def normalize_greek(text: str) -> str:
    """Upper-case, accent-free, whitespace-trimmed form for comparisons."""
    return strip_accents(text).upper().strip()
