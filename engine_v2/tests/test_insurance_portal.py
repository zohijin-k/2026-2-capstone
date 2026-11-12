"""Font-free portal insurance extraction; all values are explicitly fictitious."""
from datetime import date
from dataclasses import replace
import pytest
from engine_v2.extractors import insurance_4
from engine_v2.tests.nhis_form_samples import NAME, insurance_portal_cells, coordinate_page


def extract(cells=None):
    return insurance_4.extract([coordinate_page(insurance_portal_cells() if cells is None else cells)],
                               today=date(2026, 11, 13))


def test_portal_masked_identity_and_enrollment_contract():
    result = extract()
    assert result.form_kind == "portal"
    assert result.structure_complete is True
    assert result.fields["생년월일"].value == date(1990, 1, 1)
    assert result.fields["성명"].value == NAME
    assert result.fields["발급일"].value == date(2026, 3, 3)
    assert result.fields["발급번호"].value == "0" * 14
    assert "문서확인번호" not in result.fields
    assert all(check.passed for check in result.validations)
    assert [row.insurance_type for row in result.rows] == list(insurance_4.INSURANCE_NAMES)
    assert all(row.subscriber_name == NAME and row.management_number == "0" * 11 for row in result.rows)
    assert all(row.workplace_name.replace(" ", "") == "가짜상사가짜" for row in result.rows)
    assert all(row.acquired == date(2020, 1, 1) and row.received == date(2020, 1, 2) for row in result.rows)


@pytest.mark.parametrize("label", ["주민(외국인)등록번호", "주 민 （ 외 국 인 ） 등 록 번 호", "주민등록번호"])
def test_portal_resident_label_variants_and_right_cell(label):
    cells = [(x, y, label if x == 10 and y == 25 else text) for x, y, text in insurance_portal_cells()]
    result = extract(cells)
    assert result.fields["생년월일"].value == date(1990, 1, 1)
    assert result.structure_complete is True


@pytest.mark.parametrize("value", ["900101-1********", "900101-1******가짜", "가짜900101-1******",
                                  "900101-1****** 900101-1******", "000231-3******"])
def test_portal_rejects_ambiguous_or_malformed_rrn_cell(value):
    cells = [(x, y, value if x == 34 and y == 25 else text) for x, y, text in insurance_portal_cells()]
    result = extract(cells)
    assert "생년월일" not in result.fields
    assert result.structure_complete is False
    assert all(field.confidence < .85 for field in result.fields.values())


def test_portal_equal_acquired_received_dates_preserve_both_occurrences():
    cells = [(x, y, "(2020.01.01)" if text == "(2020.01.02)" else text)
             for x, y, text in insurance_portal_cells()]
    result = extract(cells)
    assert result.structure_complete is True
    assert all(row.acquired == row.received == date(2020, 1, 1) for row in result.rows)


@pytest.mark.parametrize("kind", ["name", "birth", "issue", "unknown", "number", "page", "row-date"])
def test_portal_incomplete_and_unknown_forms_do_not_keep_high_confidence(kind):
    cells = insurance_portal_cells()
    if kind in {"name", "birth", "issue"}:
        slot = {"name": (80, 25), "birth": (34, 25), "issue": (74, 21)}[kind]
        cells = [cell for cell in cells if cell[:2] != slot]
    elif kind == "unknown":
        cells = [cell for cell in cells if cell[2] != "확인용"]
    elif kind == "number":
        cells = [(x, y, "00000000000000가짜" if x == 30 and y == 21 else t) for x, y, t in cells]
    elif kind == "page":
        cells = [(x, y, "1 / 2" if y == 29 and x == 87 else t) for x, y, t in cells]
    else:
        cells = [(x, y, "(2020.99.99)" if x == 82 and y == 37 else t) for x, y, t in cells]
    result = extract(cells)
    assert result.structure_complete is False
    assert all(field.confidence < .85 for field in result.fields.values())
    if kind == "name":
        assert "성명" not in result.fields


def test_portal_rejects_multiple_physical_pages():
    page, words = coordinate_page(insurance_portal_cells())
    result = insurance_4.extract([(page, words), (replace(page, page=1), words)])
    assert result.structure_complete is False


def test_government24_retains_its_number_and_legacy_validations():
    from engine_v2.tests.test_insurance_4 import page, synthetic_words
    result = insurance_4.extract([page(synthetic_words())], today=date(2026, 11, 13))
    assert result.form_kind == "government24"
    assert result.structure_complete is None
    assert all(check.passed for check in result.validations)


@pytest.mark.parametrize("received", ["(2020.01.02", "2020.01.02)", "((2020.01.02))", "(2020.01.02) ()"])
def test_portal_receipt_parentheses_must_bound_one_canonical_occurrence(received):
    cells = [(x, y, received if x == 82 and y == 37 else text)
             for x, y, text in insurance_portal_cells()]
    result = extract(cells)
    assert result.structure_complete is False
    assert not next(v.passed for v in result.validations if v.name == "date_formats")


def test_portal_full_rrn_tokens_are_erased_after_birth_extraction():
    fake_number = "000101-1000000"
    cells = [(x, y, fake_number if x == 34 and y == 25 else text)
             for x, y, text in insurance_portal_cells()]
    page, raw = coordinate_page(cells)
    result = insurance_4.extract([(page, raw)])
    assert result.fields["생년월일"].value == date(1900, 1, 1)
    assert fake_number not in raw.text
    assert fake_number not in str({key: value.raw_text for key, value in result.fields.items()})


@pytest.mark.parametrize("defect", ["headings", "category-missing", "category-malformed", "management-garbage",
                                    "management-missing", "workplace-missing", "column-order"])
def test_portal_observed_columns_and_working_row_cells_are_required(defect):
    cells = insurance_portal_cells()
    if defect == "headings":
        cells = [cell for cell in cells if cell[1] not in {31, 32}]
    elif defect == "category-missing":
        cells = [cell for cell in cells if cell[:2] != (34, 40)]
    elif defect == "category-malformed":
        cells = [(x, y, "가짜미확인종별" if (x, y) == (34, 40) else text) for x, y, text in cells]
    elif defect == "management-garbage":
        cells = [(x, y, "가짜번호000" if (x, y) == (48, 40) else text) for x, y, text in cells]
    elif defect == "management-missing":
        cells = [cell for cell in cells if cell[:2] != (48, 40)]
    elif defect == "workplace-missing":
        cells = [cell for cell in cells if cell[:2] != (65, 40)]
    else:
        cells = [(48 if x == 34 else 34 if x == 48 else x, y, text) if y in {31, 32} else (x, y, text)
                 for x, y, text in cells]
    result = extract(cells)
    assert result.structure_complete is False
    assert all(field.confidence < .85 for field in result.fields.values())
    if defect == "management-garbage":
        assert result.rows[1].management_number == ""


def test_portal_regional_and_dependent_rows_may_have_empty_employment_cells():
    cells = [(x, y, "지역가입자" if (x, y) == (34, 36) else "직장피부양자" if (x, y) == (34, 40) else text)
             for x, y, text in insurance_portal_cells() if not (x in {48, 65} and y in {36, 40})]
    result = extract(cells)
    assert result.structure_complete is True
    assert result.rows[0].management_number == result.rows[1].management_number == ""
    assert result.rows[0].workplace_name == result.rows[1].workplace_name == ""


def test_portal_inactive_row_may_have_empty_cells_without_dates():
    cells = [(x, y, text) for x, y, text in insurance_portal_cells() if not (y in {44, 45} and x != 9)]
    cells.append((23, 44, "미가입"))
    result = extract(cells)
    assert result.structure_complete is True
    assert result.rows[2].status == "미가입"


def test_portal_duplicate_identity_header_erases_all_full_rrn_candidates():
    fake_number = "000101-1000000"
    cells = [(x, y, fake_number if (x, y) == (34, 25) else text) for x, y, text in insurance_portal_cells()]
    cells += [(10, 26.5, "주민(외국인)등록번호"), (34, 26.5, fake_number),
              (60, 26.5, "성명"), (80, 26.5, NAME)]
    page, raw = coordinate_page(cells)
    result = insurance_4.extract([(page, raw)])
    assert result.structure_complete is False
    assert "생년월일" not in result.fields
    assert fake_number not in raw.text
