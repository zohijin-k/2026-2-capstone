"""Own-OCR acquisition variants retain strict identity and history validation."""
from datetime import date

import pytest

from engine_v2.extractors import nhis_acquisition_loss as reader
from engine_v2.tests import p2_form_samples as sample


def extract(**kwargs):
    cells, size = sample.acquisition(**kwargs)
    return reader.extract([sample.page(cells, size=size)])


@pytest.mark.parametrize("name", ["가상", "가상인", "가상인물"])
@pytest.mark.parametrize("count", range(1, 11))
@pytest.mark.parametrize("scale,jitter,skew", [(1, 0, 0), (2, 3, 16)])
def test_region_only_history_with_gaps_empty_employers_and_blank_rows(name, count, scale, jitter, skew):
    cells, size = sample.acquisition(name=name, count=count)
    result = reader.extract([sample.page(cells, size=size, scale=scale, jitter=jitter, skew=skew)])
    assert result.structure_complete
    assert all(validation.passed for validation in result.validations)
    assert result.fields["성명"].value == name
    assert result.fields["생년월일"].value == sample.BIRTH
    assert result.fields["발급일"].value == sample.ISSUE
    assert result.fields["가입구분"].value == "지역"
    assert len(result.history) == count
    assert all(row.employer == "" for row in result.history)
    assert not result.warnings


@pytest.mark.parametrize("full_rrn", [False, True])
@pytest.mark.parametrize("gap", [False, True])
@pytest.mark.parametrize("noise", [False, True])
def test_full_or_masked_identity_and_touching_or_gapped_periods(full_rrn, gap, noise):
    result = extract(full_rrn=full_rrn, gap=gap, noise=noise)
    assert result.structure_complete
    assert result.fields["생년월일"].value == sample.BIRTH
    assert all(validation.passed for validation in result.validations)
    assert "123456" not in repr(result)


@pytest.mark.parametrize("marker,separators", [("이하여백", False), ("이 하 여 백", True),
                                                 ("==이하여백==", False)])
def test_marker_accepts_absent_and_alternate_separator_punctuation(marker, separators):
    result = extract(marker=marker, separators=separators)
    assert result.structure_complete
    assert all(validation.passed for validation in result.validations)


def test_overlap_preserves_rows_but_requires_review():
    result = extract(overlap=True)
    assert len(result.history) == 3
    assert not result.structure_complete
    assert not next(v.passed for v in result.validations if v.name == "nhis_neighbor_dates_continuous")
    assert all(field.confidence <= .4 for field in result.fields.values())


@pytest.mark.parametrize("defect", ["number", "category", "acquired", "lost", "marker-neighbor", "late-row",
                                  "nearby-employer", "far-employer", "far-latin", "far-invalid-date",
                                  "missing-header"])
def test_corrupt_or_hidden_history_evidence_is_never_ignored(defect):
    cells, size = sample.acquisition()
    if defect == "number":
        cells = [(*cell[:4], "I" if cell[4] == "2" else cell[4], cell[5]) for cell in cells]
    elif defect == "category":
        cells = [(*cell[:4], "지역세대오독" if cell[4] == "지역세대주" else cell[4], cell[5]) for cell in cells]
    elif defect in {"acquired", "lost"}:
        x = 1652 if defect == "acquired" else 2048
        cells = [(*cell[:4], "2020.99.99" if cell[0] == x and cell[1] == 1243 else cell[4], cell[5])
                 for cell in cells]
    elif defect == "marker-neighbor":
        cells.append(sample.cell(258, 1489, 474, 1544, "지역세대원", 1))
    elif defect == "late-row":
        cells.extend([sample.cell(185, 2100, 230, 2148, "4", 1),
                      sample.cell(258, 2100, 474, 2148, "지역세대원", 1),
                      sample.cell(1652, 2100, 1867, 2146, "2009.01.01", 1)])
    elif defect == "nearby-employer":
        cells.append(sample.cell(845, 1600, 1105, 1650, "가상사업장", .99))
    elif defect in {"far-employer", "far-latin", "far-invalid-date"}:
        text = {"far-employer": "가상사업장", "far-latin": "FAKECORP", "far-invalid-date": "2020.99.99"}[defect]
        cells.append(sample.cell(845, 2100, 1105, 2150, text, .99))
    else:
        cells = [cell for cell in cells if cell[4] != "사업장명칭"]
    result = reader.extract([sample.page(cells, size=size)])
    assert not result.structure_complete
    assert any(not validation.passed for validation in result.validations)
    assert all(field.confidence <= .4 for field in result.fields.values())


def test_five_year_listing_meaning_accepts_old_loss_with_gaps():
    issue = date(2026, 3, 3)
    rows = [(date(2024, 1, 1), None), (date(2020, 1, 1), date(2023, 1, 1)),
            (date(2016, 1, 1), date(2019, 1, 1))]
    assert reader.history_covers_recent_years(issue, None, rows)
    assert not reader.history_covers_recent_years(issue, None, rows[:2])
    assert not reader.history_covers_recent_years(issue, (date(2022, 1, 1), issue), rows)
