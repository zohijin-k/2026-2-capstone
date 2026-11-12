"""Entirely authored fake histories; no values originate from user documents."""
from engine_v2.tests.nhis_form_samples import acquisition_cells

ISSUE = "2031-07-08"


def cells_for(case="complete", marker="이하여백"):
    cells = [(x, y, text) for x, y, text in acquisition_cells()
             if case == "old" or y != 47]
    dates = {(65, 37): "2030.01.01", (65, 42): "2028.01.01",
             (81, 42): "2029.01.01", (43, 72): "2031.07.08"}
    cells = [(x, y, dates.get((x, y), marker if text == "이하여백" else text))
             for x, y, text in cells]
    if case == "missing-marker":
        cells = [(x, y, text) for x, y, text in cells if y != 52]
    elif case == "bad-structure":
        cells = [(x, y, "8" if (x, y) == (7, 42) else text) for x, y, text in cells]
    elif case in {"short-period", "full-period", "unreadable-period"}:
        cells.append((10, 29, "조 회 기 간"))
        if case != "unreadable-period":
            cells += [(30, 29, "2028.01.01" if case == "short-period" else "2020.01.01"),
                      (50, 29, "~"), (55, 29, "2031.07.08")]
    return cells


def own_cells(cells):
    return [(x * 20, y * 28, (x + len(text) * .8) * 20, (y + .8) * 28, text, .99)
            for x, y, text in cells]
