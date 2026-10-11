"""Table-detection tests for hospitals.parser.

The edge coordinates below were captured from real Ministry PDFs (the fdl id is
named in each test). A row the page break leaves without a bottom border used
to vanish from pdfplumber's line-based tables; _table_settings closes it.
"""

from types import SimpleNamespace

from hospitals.models import Window
from hospitals.parser import _split_cell_into_hospitals, _table_settings

DAY = Window(start="08:00", end="08:00", crosses_midnight=True)


def edge(orientation: str, top: float, bottom: float) -> dict:
    return {"orientation": orientation, "top": top, "bottom": bottom}


def test_open_last_row_is_closed_where_the_verticals_end():
    # fdl 31903 page 0: Γαστρεντερολογική starts at the y=726 rule; its verticals
    # run on to y=799 with no horizontal rule beneath them.
    page = SimpleNamespace(
        edges=[
            edge("h", 726.0, 726.0),
            edge("v", 710.0, 726.0),
            edge("v", 726.0, 775.0),
            edge("v", 775.0, 799.0),
        ]
    )
    assert _table_settings(page) == {"explicit_horizontal_lines": [799.0]}


def test_page_without_vertical_rules_keeps_default_settings():
    page = SimpleNamespace(edges=[edge("h", 100.0, 100.0)])
    assert _table_settings(page) == {}


def test_symbol_font_space_is_not_a_hospital():
    # fdl 31902, Ω.Ρ.Λ.: one cell holds only U+F020, another trails it.
    assert _split_cell_into_hospitals("", DAY) == []
    names = [h.name for h in _split_cell_into_hospitals("Γ.Ν.Π. «ΤΖΑΝΕΙΟ» ", DAY)]
    assert names == ["Γ.Ν.Π. «ΤΖΑΝΕΙΟ»"]
