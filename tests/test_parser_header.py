"""Header-row detection tests for hospitals.parser.

The Ministry is inconsistent about the case of the repeated header cell. In the
2026-07-16 PDF (fdl 31363) pages 0-2 spell it "ΚΛΙΝΙΚΕΣ" while page 3 spells it
"Κλινικές". Because the header row is what teaches the parser its time-window
columns, failing to recognise it means every row on those pages yields no
hospitals at all and is then dropped as empty — that PDF produced 5 specialties
instead of 28.
"""

from hospitals.parser import _is_header_label
from hospitals.text import normalize_greek


def test_mixed_case_header_recognised():
    # fdl 31363 page 3, and every page of a normal day.
    assert _is_header_label("Κλινικές")


def test_all_caps_accentless_header_recognised():
    # fdl 31363 pages 0-2 — the spelling that used to be missed.
    assert _is_header_label("ΚΛΙΝΙΚΕΣ")


def test_accented_all_caps_header_recognised():
    assert _is_header_label("ΚΛΙΝΙΚΈΣ")


def test_header_recognised_with_surrounding_whitespace():
    assert _is_header_label("  ΚΛΙΝΙΚΕΣ \n")


def test_specialty_names_are_not_mistaken_for_the_header():
    for label in (
        "Παθολογική",
        "Καρδιολογική",
        "Παιδιατρικό",
        "Κλινική Χεριού- Μικροχειρουργική Άνω Άκρου",
        "",
    ):
        assert not _is_header_label(label), label


def test_normalize_greek_folds_case_and_accents():
    assert normalize_greek("Κλινικές") == normalize_greek("ΚΛΙΝΙΚΕΣ")
    assert normalize_greek("ΜΑΪΟΥ") == normalize_greek("ΜΑΙΟΥ")
    assert normalize_greek("  έως  ") == "ΕΩΣ"


def test_normalize_greek_keeps_distinct_words_distinct():
    assert normalize_greek("Παθολογική") != normalize_greek("Καρδιολογική")
