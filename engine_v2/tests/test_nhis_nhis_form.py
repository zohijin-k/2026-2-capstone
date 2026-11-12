"""Font-free NHIS form/structure regressions with fictitious values."""
from datetime import date
from dataclasses import replace
import pytest

from engine_v2.extractors import nhis_acquisition_loss as acquisition
from engine_v2.extractors import nhis_common as common
from engine_v2.tests.nhis_form_samples import NAME, acquisition_cells, coordinate_page


def test_nhis_normal_extracts_identity_internal_number_and_bounded_history():
    result = acquisition.extract([coordinate_page()])
    assert result.form_kind == "nhis"
    assert result.structure_complete is True
    assert result.document_number == "G" + "0" * 18
    assert "발급번호" not in result.fields
    assert result.fields["성명"].value == NAME
    assert result.fields["생년월일"].value == "1990-01-01"
    assert result.fields["발급일"].value == "2026-03-03"
    assert [(row.number, row.category, row.employer) for row in result.history] == [
        (1, "직장가입자", "가짜상사 (FAKE,Corp)"),
        (2, "지역세대주", ""),
        (3, "직장피부양자", "가짜센터(가짜사업부)"),
    ]
    assert result.history[0].acquired == date(2024, 1, 1)
    assert result.history[0].lost is None
    assert result.history[1].lost == date(2024, 1, 1)
    assert all(check.passed for check in result.validations)


@pytest.mark.parametrize("gender", "12345678")
def test_shared_masked_rrn_century_mapping_matches_legacy_header(gender):
    value = f"000101-{gender}******"
    expected = date(2000 if gender in "3478" else 1900, 1, 1)
    cells = [(x, y, value if text == "900101-1******" else text)
             for x, y, text in acquisition_cells()]
    result = acquisition.extract([coordinate_page(cells)])
    assert common.birth_from_rrn(value) == expected
    assert result.fields["생년월일"].value == expected.isoformat()


@pytest.mark.parametrize("kind", ["name", "birth", "issue", "number", "marker", "sequence",
                                  "neighbor", "current-loss", "page-count", "no-column",
                                  "conflicting-form", "ambiguous-date", "date-outside-block"])
def test_nhis_missing_or_inconsistent_structure_never_has_complete_confidence(kind):
    cells = acquisition_cells()
    if kind == "name":
        cells = [cell for cell in cells if cell[2] != NAME]
    elif kind == "birth":
        cells = [cell for cell in cells if cell[2] != "900101-1******"]
    elif kind == "issue":
        cells = [cell for cell in cells if cell[1] != 72]
    elif kind == "number":
        cells = [(x, y, "발급번호 : G000" if y == 8 else text) for x, y, text in cells]
    elif kind == "marker":
        cells = [cell for cell in cells if cell[1] != 52]
    elif kind == "sequence":
        cells = [(x, y, "9" if x == 7 and y == 42 else text) for x, y, text in cells]
    elif kind == "neighbor":
        cells = [(x, y, "2023.01.01" if x == 81 and y == 42 else text) for x, y, text in cells]
    elif kind == "current-loss":
        cells.append((81, 37, "2025.01.01"))
    elif kind == "page-count":
        cells = [(x, y, "1 / 2" if y == 4 else text) for x, y, text in cells]
    elif kind == "no-column":
        cells = [cell for cell in cells if cell[2] != "No"]
    elif kind == "conflicting-form":
        cells.append((10, 6, "문서확인번호"))
    elif kind == "ambiguous-date":
        cells.append((43, 74, "2026.03.03"))
    elif kind == "date-outside-block":
        cells = [(x, 78 if y == 72 else y, text) for x, y, text in cells]
    result = acquisition.extract([coordinate_page(cells)])
    assert result.structure_complete is False
    assert any(not check.passed for check in result.validations)
    assert all(field.confidence < .85 for field in result.fields.values())


def test_nhis_physical_multiple_pages_are_incomplete_but_government24_is_unchanged():
    page, words = coordinate_page()
    result = acquisition.extract([(page, words), (replace(page, page=1), words)])
    assert result.form_kind == "nhis"
    assert result.structure_complete is False
    from engine_v2.tests.test_nhis_continuation_identity import _page
    legacy = acquisition.extract([_page(0, labeled_issue=True), _page(1, identity=False)])
    assert legacy.form_kind == "government24"
    assert legacy.structure_complete is None
    assert next(check.passed for check in legacy.validations if check.name == "document_confirmation_number_consistent")


def test_unknown_body_signature_is_reviewable_instead_of_assuming_government24():
    cells = [(10, 10, "건강보험자격득실확인서"), (10, 20, "알수없는가짜양식")]
    result = acquisition.extract([coordinate_page(cells)])
    assert result.form_kind == "unknown"
    assert result.structure_complete is False
    assert not next(check.passed for check in result.validations if check.name == "form_recognized")


def test_long_multiword_employer_crosses_date_columns_without_stealing_dates():
    cells = [cell for cell in acquisition_cells() if not (cell[0] == 33 and cell[1] == 37)]
    cells.extend([(33, 37, "가짜상사 (FAKE,Corp) 가짜긴사업부"),
                  (52, 37, "가짜센터"), (57, 37, "가짜부서")])
    result = acquisition.extract([coordinate_page(cells)])
    assert result.structure_complete is True
    assert result.history[0].employer == "가짜상사 (FAKE,Corp) 가짜긴사업부 가짜센터 가짜부서"
    assert result.history[0].acquired == date(2024, 1, 1)
    assert result.history[0].lost is None
    assert result.history[1].employer == ""


def test_acquisition_shaped_unknown_table_is_not_guessed_as_government24():
    cells = [cell for cell in acquisition_cells() if not any(
        cue in common.squash(cell[2]) for cue in ("발급번호", "확인청구자", "자격득실확인내역"))]
    result = acquisition.extract([coordinate_page(cells)])
    assert result.form_kind == "unknown"
    assert result.structure_complete is False


def test_marker_in_date_column_is_not_a_valid_end_marker():
    cells = [(70 if text == "이하여백" else x, y, text) for x, y, text in acquisition_cells()]
    result = acquisition.extract([coordinate_page(cells)])
    assert result.structure_complete is False
    assert not next(v.passed for v in result.validations if v.name == "nhis_blank_marker")


@pytest.mark.parametrize("extra", [(28, 23, "가짜다름"), (55, 23, "900101-1******")])
def test_competing_identity_value_rows_are_not_complete(extra):
    result = acquisition.extract([coordinate_page([*acquisition_cells(), extra])])
    assert result.structure_complete is False
    label = "성명" if extra[0] == 28 else "생년월일"
    assert label not in result.fields
    assert not next(v.passed for v in result.validations if v.name == f"{label}_consistent")


def test_malformed_second_date_is_not_ignored_in_closing_block():
    cells = [*acquisition_cells(), (43, 74, "2026.99.99")]
    result = acquisition.extract([coordinate_page(cells)])
    assert result.structure_complete is False
    assert "발급일" not in result.fields
    assert not next(v.passed for v in result.validations if v.name == "nhis_issue_location_unique")
