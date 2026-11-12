"""Own-OCR qualification variants preserve complete household publication."""
import json

import pytest

from engine_v2.extractors import nhis_qualification as reader
from engine_v2.tests import p2_form_samples as sample


def extract(**kwargs):
    cells, size = sample.qualification(**kwargs)
    return reader.extract([sample.page(cells, size=size)])


@pytest.mark.parametrize("name", ["가상", "가상인", "가상인물"])
@pytest.mark.parametrize("count", range(1, 11))
@pytest.mark.parametrize("scale,jitter,skew", [(1, 0, 0), (2, 3, 16)])
def test_one_to_ten_members_with_empty_optional_columns_and_ocr_geometry(name, count, scale, jitter, skew):
    cells, size = sample.qualification(name=name, count=count)
    result = reader.extract([sample.page(cells, size=size, scale=scale, jitter=jitter, skew=skew)])
    assert result.structure_complete
    assert all(validation.passed for validation in result.validations)
    assert result.fields["성명"].value == name
    assert result.fields["생년월일"].value == sample.BIRTH
    assert result.fields["발급일"].value == sample.ISSUE
    assert result.fields["가구원수"].value == str(count)
    members = json.loads(result.fields["가구원목록"].value)
    assert len(members) == count
    assert members[0]["성명"] == name
    assert all(member["자격상실일"] == "" for member in members)
    assert not result.warnings


@pytest.mark.parametrize("same_dates", [False, True])
@pytest.mark.parametrize("empty_management", [False, True])
@pytest.mark.parametrize("noise", [False, True])
def test_request_and_validity_dates_are_separate_from_unique_issue_date(same_dates, empty_management, noise):
    result = extract(same_dates=same_dates, empty_management=empty_management, noise=noise)
    assert result.structure_complete
    assert result.fields["발급일"].value == sample.ISSUE
    assert result.fields["자격확인요청일"].value == (sample.ISSUE if same_dates else "2026-03-01")
    assert result.valid_until.isoformat() == (sample.ISSUE if same_dates else "2026-04-03")
    assert all(validation.passed for validation in result.validations)


@pytest.mark.parametrize("marker,separators", [("이하여백", False), ("이 하 여 백", True),
                                                 ("==이하여백==", False)])
def test_marker_accepts_observed_absent_or_different_separator_punctuation(marker, separators):
    assert extract(marker=marker, separators=separators).structure_complete


@pytest.mark.parametrize("defect", ["name", "birth", "acquired", "loss", "same-date-twice", "bad-issue",
                                  "extra-member", "far-name", "far-date", "marker-neighbor", "missing-header"])
def test_incomplete_or_hidden_member_prevents_authoritative_household_count(defect):
    cells, size = sample.qualification()
    if defect in {"name", "birth", "acquired"}:
        x = {"name": 155, "birth": 413, "acquired": 959}[defect]
        cells = [cell for cell in cells if not (cell[0] == x and 1481 <= cell[1] < 1590)]
    elif defect == "loss":
        cells.append(sample.cell(1301, 1488, 1540, 1539, "2020.99.99", 1))
    elif defect in {"same-date-twice", "bad-issue"}:
        text = "2026.03.03" if defect == "same-date-twice" else "2026.99.99"
        cells.append(sample.cell(1114, 2830, 1375, 2893, text, 1))
    elif defect in {"extra-member", "far-name", "far-date"}:
        text = "2009.01.01" if defect == "far-date" else "가상누락"
        x = 959 if defect == "far-date" else 155
        y = 1710 if defect == "extra-member" else 2100
        cells.append(sample.cell(x, y, x + 220, y + 55, text, .99))
    elif defect == "marker-neighbor":
        cells.append(sample.cell(155, 1596, 295, 1651, "가상누락", 1))
    else:
        cells = [cell for cell in cells if cell[4] != "자격상실일"]
    result = reader.extract([sample.page(cells, size=size)])
    assert not result.structure_complete
    assert any(not validation.passed for validation in result.validations)
    assert "가구원수" not in result.fields
    assert "가구원목록" not in result.fields
    assert all(field.confidence <= .4 for field in result.fields.values())
