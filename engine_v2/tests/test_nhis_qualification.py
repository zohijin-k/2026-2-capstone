"""Font-free authored notification-form extraction and household safety."""
import json
from dataclasses import replace
from datetime import date

import pytest

from engine_v2.extractors import nhis_qualification as qualification
from engine_v2.tests.nhis_form_samples import NAME, coordinate_page, qualification_cells


def test_notification_identity_members_and_internal_dates_are_separate():
    result = qualification.extract([coordinate_page(qualification_cells())])
    assert result.form_kind == "nhis"
    assert result.structure_complete is True
    assert all(check.passed for check in result.validations)
    assert result.fields["성명"].value == NAME
    assert result.fields["생년월일"].value == "1990-01-01"
    assert result.fields["발급일"].value == "2026-03-03"
    assert result.document_number == "0-0000-20260301-000000"
    assert result.request_date == date(2026, 3, 1)
    assert result.fields["자격확인요청일"].value == "2026-03-01"
    assert result.valid_until == date(2026, 4, 3)
    assert result.fields["가구원수"].value == "2"
    assert json.loads(result.fields["가구원목록"].value) == [
        {"성명": NAME, "생년월일": "1990-01-01", "자격취득일": "2020-01-01", "자격상실일": ""},
        {"성명": "가짜가족", "생년월일": "2001-01-01", "자격취득일": "2021-01-01", "자격상실일": ""},
    ]
    for key in ("통보번호", "유효기간", "가입구분"):
        assert key not in result.fields
    assert result.document_number not in repr(result)


@pytest.mark.parametrize("gender", "1234")
def test_member_masked_rrn_century_uses_existing_mapping(gender):
    cells = [(x, y, f"000101-{gender}******" if x == 27 and y == 51 else text)
             for x, y, text in qualification_cells()]
    result = qualification.extract([coordinate_page(cells)])
    assert result.structure_complete
    members = json.loads(result.fields["가구원목록"].value)
    assert members[1]["생년월일"] == f"{2000 if gender in '34' else 1900}-01-01"


@pytest.mark.parametrize("kind", ["issue", "ambiguous-issue", "invalid-issue", "issue-outside",
                                  "marker", "misplaced-marker", "subscriber-name", "subscriber-birth",
                                  "member-name", "member-birth", "member-acquired", "first-member",
                                  "notice", "page-marker", "unknown-form", "extra-row"])
def test_incomplete_notification_cannot_produce_authoritative_household_count(kind):
    cells = qualification_cells()
    remove = {"issue": (42, 72), "marker": (49, 55), "subscriber-name": (29, 32),
              "subscriber-birth": (55, 32), "member-name": (10, 51),
              "member-birth": (27, 51), "member-acquired": (49, 51), "notice": (10, 14)}
    if kind in remove:
        cells = [cell for cell in cells if cell[:2] != remove[kind]]
    elif kind == "ambiguous-issue":
        cells.append((42, 74, "2026.03.03"))
    elif kind == "invalid-issue":
        cells.append((42, 74, "2026.99.99"))
    elif kind == "issue-outside":
        cells = [(x, 79 if y == 72 else y, t) for x, y, t in cells]
    elif kind == "misplaced-marker":
        cells = [(70 if t == "이하여백" else x, y, t) for x, y, t in cells]
    elif kind == "first-member":
        cells = [(x, y, "가짜다름" if x == 10 and y == 47 else t) for x, y, t in cells]
    elif kind == "page-marker":
        cells = [(x, y, "1 / 2" if y == 4 else t) for x, y, t in cells]
    elif kind == "unknown-form":
        cells = [cell for cell in cells if cell[2] != "자 격 확 인 내 역"]
    elif kind == "extra-row":
        cells.append((10, 57, "가짜누락"))
    result = qualification.extract([coordinate_page(cells)])
    assert result.structure_complete is False
    assert any(not check.passed for check in result.validations)
    assert "가구원목록" not in result.fields
    assert "가구원수" not in result.fields
    assert all(field.confidence < .85 for field in result.fields.values())
    if "issue" in kind:
        assert "발급일" not in result.fields


def test_physical_multiple_pages_never_become_a_single_supported_notification():
    page, words = coordinate_page(qualification_cells())
    result = qualification.extract([(page, words), (replace(page, page=1), words)])
    assert result.structure_complete is False
    assert "가구원목록" not in result.fields


def test_optional_loss_date_is_preserved_and_not_shifted_from_blank_cell():
    cells = [*qualification_cells(), (65, 51, "2025.01.01")]
    result = qualification.extract([coordinate_page(cells)])
    assert result.structure_complete
    members = json.loads(result.fields["가구원목록"].value)
    assert members[0]["자격상실일"] == ""
    assert members[1]["자격상실일"] == "2025-01-01"


@pytest.mark.parametrize("value", ["가짜문자010101-3******", "010101-3******010101-3******", "010199-3******"])
def test_member_identity_cell_cannot_hide_garbage_or_duplicate_numbers(value):
    cells = [(x, y, value if x == 27 and y == 51 else text)
             for x, y, text in qualification_cells()]
    result = qualification.extract([coordinate_page(cells)])
    assert result.structure_complete is False
    assert "가구원목록" not in result.fields


def test_ambiguous_request_date_is_not_a_new_eligibility_rule_or_an_issue_candidate():
    cells = [*qualification_cells(), (78, 20, "2026.03.02")]
    # A second labeled request value is ambiguous metadata, not an issuance date.
    cells.extend([(57, 24, "자격확인요청일"), (78, 24, "2026.03.02")])
    result = qualification.extract([coordinate_page(cells)])
    assert result.structure_complete is True
    assert result.request_date is None
    assert "자격확인요청일" not in result.fields
    assert result.fields["발급일"].value == "2026-03-03"


@pytest.mark.parametrize("defect", ["member-on-marker", "extra-marker-text", "header-identifier-garbage"])
def test_marker_and_subscriber_identifier_must_be_complete_cell_shapes(defect):
    cells = qualification_cells()
    if defect == "member-on-marker":
        cells = [(x, y, "가짜누락" if x == 10 and y == 55 else
                  "020202-3******" if x == 27 and y == 55 else text) for x, y, text in cells]
    elif defect == "extra-marker-text":
        cells = [(x, y, "이하여백가짜" if text == "이하여백" else text) for x, y, text in cells]
    else:
        cells = [(x, y, "가짜문자900101-1******" if x == 55 and y == 32 else text)
                 for x, y, text in cells]
    result = qualification.extract([coordinate_page(cells)])
    assert result.structure_complete is False
    assert "가구원목록" not in result.fields
    assert "가구원수" not in result.fields


@pytest.mark.parametrize("value", ["가짜문자900101-1******", "900101-1******가짜", "900101-1********"])
@pytest.mark.parametrize("form", ["acquisition", "qualification"])
def test_shared_person_value_cell_rejects_identifier_residue_and_overlong_masks(value, form):
    from engine_v2.extractors import nhis_acquisition_loss
    from engine_v2.tests.nhis_form_samples import acquisition_cells
    cells = acquisition_cells() if form == "acquisition" else qualification_cells()
    row_y = 22 if form == "acquisition" else 32
    cells = [(x, y, value if x == 55 and y == row_y else text) for x, y, text in cells]
    extractor = nhis_acquisition_loss if form == "acquisition" else qualification
    result = extractor.extract([coordinate_page(cells)])
    assert result.structure_complete is False
    assert "생년월일" not in result.fields


def test_shared_person_header_allows_merged_label_and_value_without_residue():
    cells = [(x, y, "주민등록번호900101-1******" if x == 55 and y == 28 else text)
             for x, y, text in qualification_cells() if not (x == 55 and y == 32)]
    result = qualification.extract([coordinate_page(cells)])
    assert result.structure_complete is True
    assert result.fields["생년월일"].value == "1990-01-01"
