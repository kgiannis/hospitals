"""Cell-grouping tests for hospitals.parser.

Every ``cell`` string below was captured verbatim from a real Ministry PDF (the
fdl id is named in each test), so these double as a fixture corpus for a parser
that otherwise can only be exercised against the live site.
"""

from hospitals.parser import _group_cell_entries, _split_cell_into_hospitals
from hospitals.models import Window

DAY = Window(start="08:00", end="08:00", crosses_midnight=True)


def names(cell: str) -> list[str]:
    return [h.name for h in _split_cell_into_hospitals(cell, DAY)]


# --- ΠΕΙΡΑΙΑΣ is a stray label, never a hospital ------------------------------
# It heads a cell (fdl 31191), sits mid-cell (fdl 31214), and is followed by
# hospitals nowhere near Piraeus — Γ.Ν.Ε. «ΘΡΙΑΣΙΟ» is in Elefsina — so it
# cannot be read as "the hospital below is the Piraeus one". It is dropped.


def test_label_at_start_of_cell_is_dropped():
    # fdl 31191, Παθολογική, 24h column.
    assert names("ΠΕΙΡΑΙΑΣ\nΓ.Ν.Ν. «ΑΓ. ΠΑΝΤΕΛΕΗΜΩΝ»") == [
        "Γ.Ν.Ν. «ΑΓ. ΠΑΝΤΕΛΕΗΜΩΝ»"
    ]


def test_label_mid_cell_is_dropped_and_does_not_merge_into_neighbours():
    # fdl 31214. The label must not glue onto «ΚΑΤ» above it, nor onto
    # «ΘΡΙΑΣΙΟ» below it.
    cell = "Γ.Ν.Α. «ΚΑΤ»\nΠΕΙΡΑΙΑΣ\nΓ.Ν.Ε. «ΘΡΙΑΣΙΟ»"
    assert names(cell) == ["Γ.Ν.Α. «ΚΑΤ»", "Γ.Ν.Ε. «ΘΡΙΑΣΙΟ»"]


def test_label_with_trailing_punctuation_is_dropped():
    # The single "ΠΕΙΡΑΙΑΣ ," variant seen across 22 PDFs.
    assert names("ΠΕΙΡΑΙΑΣ ,\nΓ.Ν.Π. «ΤΖΑΝΕΙΟ»") == ["Γ.Ν.Π. «ΤΖΑΝΕΙΟ»"]


def test_label_never_appears_as_a_hospital_name():
    for cell in (
        "ΠΕΙΡΑΙΑΣ\nΕ.Α.Ν.Π. «ΜΕΤΑΞΑ»",
        "Γ.Ν.Α. «ΑΛΕΞΑΝΔΡΑ»\nΠΕΙΡΑΙΑΣ\nΓ.Ν.Ν. «ΑΓ. ΠΑΝΤΕΛΕΗΜΩΝ»",
        "ΠΕΙΡΑΙΑΣ\nΠ.Γ.Ν. «ΑΤΤΙΚΟΝ»\nΓ.Ν. «ΑΣΚΛΗΠΙΕΙΟ»\nΒΟΥΛΑΣ",
    ):
        assert not any("ΠΕΙΡΑΙΑΣ" in n for n in names(cell)), cell


def test_hospital_after_the_label_survives_even_without_an_abbrev_prefix():
    # A bare (non-"Γ.Ν.Α.") name following the label must still open its own
    # entry rather than being swallowed as a wrapped continuation.
    cell = "Γ.Ν.Α. «ΚΑΤ»\nΠΕΙΡΑΙΑΣ\nΚΡΑΤΙΚΟ ΝΙΚΑΙΑΣ"
    assert names(cell) == ["Γ.Ν.Α. «ΚΑΤ»", "ΚΡΑΤΙΚΟ ΝΙΚΑΙΑΣ"]


# --- pre-existing behaviour that must not regress ----------------------------


def test_wrapped_name_still_joins():
    # fdl 31210: «ΑΣΚΛΗΠΙΕΙΟ» / ΒΟΥΛΑΣ is one hospital split over two lines.
    cell = "ΠΕΙΡΑΙΑΣ\nΠ.Γ.Ν. «ΑΤΤΙΚΟΝ»\nΓ.Ν. «ΑΣΚΛΗΠΙΕΙΟ»\nΒΟΥΛΑΣ"
    assert names(cell) == ["Π.Γ.Ν. «ΑΤΤΙΚΟΝ»", "Γ.Ν. «ΑΣΚΛΗΠΙΕΙΟ» ΒΟΥΛΑΣ"]


def test_inline_override_after_the_label_still_parsed():
    # fdl 31210: the override moves the window and becomes the note.
    cell = "ΠΕΙΡΑΙΑΣ\nΠ.Γ.Ν. «ΑΤΤΙΚΟΝ» έως 21:00"
    hospitals = _split_cell_into_hospitals(cell, DAY)
    assert [h.name for h in hospitals] == ["Π.Γ.Ν. «ΑΤΤΙΚΟΝ»"]
    assert hospitals[0].note == "έως 21:00"
    assert hospitals[0].window.end == "21:00"
    assert hospitals[0].window.crosses_midnight is False


def test_override_on_a_wrapped_name_after_the_label():
    # fdl 31191: name wraps AND carries an override on the wrapped line.
    cell = (
        "ΠΕΙΡΑΙΑΣ\nΓ.Ν.Ν. «ΑΓ. ΠΑΝΤΕΛΕΗΜΩΝ»\nΓ.Ν.Α. «ΚΑΤ»\n"
        "Γ.Ν. «ΑΣΚΛΗΠΙΕΙΟ» ΒΟΥΛΑΣ ΕΩΣ\n21:00"
    )
    hospitals = _split_cell_into_hospitals(cell, DAY)
    assert [h.name for h in hospitals] == [
        "Γ.Ν.Ν. «ΑΓ. ΠΑΝΤΕΛΕΗΜΩΝ»",
        "Γ.Ν.Α. «ΚΑΤ»",
        "Γ.Ν. «ΑΣΚΛΗΠΙΕΙΟ» ΒΟΥΛΑΣ",
    ]
    assert hospitals[-1].window.end == "21:00"


def test_polydynami_is_a_real_hospital_and_still_starts_an_entry():
    # ΠΟΛΥΔΥΝΑΜΗ ... (ΔΑΦΝΙ) has no abbreviation prefix but IS a hospital,
    # unlike ΠΕΙΡΑΙΑΣ. It must keep opening its own entry.
    cell = (
        "Γ.Ν.Α. «ΚΑΤ»\n"
        "ΠΟΛΥΔΥΝΑΜΗ ΝΟΣΗΛΕΥΤΙΚΗ ΜΟΝΑΔΑ ΨΥΧΙΚΗΣ ΥΓΕΙΑΣ ΑΤΤΙΚΗ (ΔΑΦΝΙ)"
    )
    assert names(cell) == [
        "Γ.Ν.Α. «ΚΑΤ»",
        "ΠΟΛΥΔΥΝΑΜΗ ΝΟΣΗΛΕΥΤΙΚΗ ΜΟΝΑΔΑ ΨΥΧΙΚΗΣ ΥΓΕΙΑΣ ΑΤΤΙΚΗ (ΔΑΦΝΙ)",
    ]


def test_plain_cell_unchanged():
    cell = "Γ.Ν.Α. «ΛΑΪΚΟ»\nΓ.Ν.Α. «ΕΛΠΙΣ»\nΓ.Ν.Α. «ΣΙΣΜΑΝΟΓΛΕΙΟ»"
    assert names(cell) == [
        "Γ.Ν.Α. «ΛΑΪΚΟ»",
        "Γ.Ν.Α. «ΕΛΠΙΣ»",
        "Γ.Ν.Α. «ΣΙΣΜΑΝΟΓΛΕΙΟ»",
    ]


def test_empty_cell_yields_nothing():
    assert names("") == []
    assert _group_cell_entries("\n \n") == []


def test_a_cell_that_is_only_the_label_yields_no_hospitals():
    assert names("ΠΕΙΡΑΙΑΣ") == []
