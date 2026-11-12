"""Bounded eight-column payment extraction and conservative OCR correction."""
import json

import pytest

from engine_v2.extractors import nhis_payment
from engine_v2.pipeline.preprocess import PageSource
from engine_v2.tests import p2_payment_samples as sample


def extraction(**options):
    cells, size = sample.payment(**options)
    return nhis_payment.extract([sample.page(cells, size=size)])


@pytest.mark.parametrize("corrected", [False, True])
@pytest.mark.parametrize("optional", [False, True])
@pytest.mark.parametrize("paid_different", [False, True])
def test_payment_reads_all_eight_columns_and_preserves_empty_cells(corrected, optional, paid_different):
    result = extraction(corrected=corrected, optional=optional, paid_different=paid_different)
    assert result.structure_complete, [(v.name, v.passed) for v in result.validations]
    assert all(v.passed for v in result.validations)
    assert result.warnings == []
    assert result.fields["성명"].value == sample.NAME
    assert result.fields["생년월일"].value == sample.BIRTH
    assert result.fields["발급일"].value == sample.ISSUE
    assert result.fields["사업장명칭"].value == ""
    assert result.fields["납부자번호"].value == "00000000000"
    assert result.fields["문서확인번호"].value == "0000-0000-0000-00000"
    assert result.fields["용도구분"].value == "납부확인용"
    assert json.loads(result.fields["조회기간"].value) == ["2025-10", "2025-12"]
    billed = json.loads(result.fields["월별고지금액"].value)
    assert list(billed) == [f"2025-{month:02}" for month in range(1, 13)]
    assert billed["2025-01"] == "0"
    assert billed["2025-10"] == "100000"
    assert result.fields["건강보험료"].value == "50000"
    assert result.fields["장기요양보험료"].value == "5000"
    assert "가입구분" not in result.fields
    rows = json.loads(result.fields["월별납부내역"].value)
    assert rows[0]["고지"]["보수외소득월액(건강)"] is None
    assert rows[9]["고지"]["보수외소득월액(건강)"] == ("1000" if optional else None)
    assert rows[9]["납부"]["건강보험료"] == ("50000" if paid_different else "100000")
    expected_total = 166100 if optional else 165000
    assert result.fields["납부총액"].value == str(expected_total // 2 if paid_different else expected_total)
    assert "숫자형식교정" in result.fields if corrected else "숫자형식교정" not in result.fields


@pytest.mark.parametrize("name", ["가상", "가상인", "가상인명"])
@pytest.mark.parametrize("scale,jitter,skew", [(.7, 0, 0), (1, 3, 14), (1.7, 4, -12)])
@pytest.mark.parametrize("trailing_blank", [False, True])
def test_payment_geometry_and_name_length_variants(name, scale, jitter, skew, trailing_blank):
    cells, size = sample.payment(name=name, corrected=True, trailing_blank=trailing_blank)
    pages = [sample.page(cells, size=size, scale=scale, jitter=jitter, skew=skew)]
    result = nhis_payment.extract(pages)
    assert result.structure_complete, [(v.name, v.passed) for v in result.validations]
    assert result.fields["성명"].value == name
    assert result.warnings == []


@pytest.mark.parametrize("defect", ["unknown-glyph", "arithmetic", "grand-total", "missing-month", "duplicate-month",
                                  "missing-header", "missing-name", "missing-birth", "bad-grouping", "extra-token",
                                  "missing-sum", "missing-purpose", "missing-issue", "empty-required"])
def test_damaged_payment_never_becomes_complete(defect):
    cells, size = sample.payment(corrected=True)
    if defect in {"unknown-glyph", "arithmetic", "bad-grouping", "empty-required"}:
        text = {"unknown-glyph": "A", "arithmetic": "I00.001", "bad-grouping": "I0.00", "empty-required": ""}[defect]
        cells = [(*cell[:4], text, cell[5]) if cell[4] == "I00.000" else cell for cell in cells]
    elif defect == "grand-total":
        cells = [(*cell[:4], "165,001", cell[5]) if cell[0] == 738 else cell for cell in cells]
    elif defect == "missing-month":
        cells = [cell for cell in cells if not (cell[4] == "4월")]
    elif defect == "duplicate-month":
        cells.append(sample.cell(196, 1139, 258, 1193, "4월", 1))
    elif defect == "missing-header":
        cells = [cell for cell in cells if not (cell[4] == "소득월액" and cell[0] > 1700)]
    elif defect in {"missing-name", "missing-birth", "missing-purpose", "missing-issue", "missing-sum"}:
        text = {"missing-name": sample.NAME, "missing-birth": "1990.01.01.", "missing-purpose": "납부확인용",
                "missing-issue": "2026 년 03 월 03 일", "missing-sum": "합계"}[defect]
        cells = [cell for cell in cells if cell[4] != text]
    elif defect == "extra-token":
        cells.append(sample.cell(430, 962, 465, 1011, "값", .99))
    result = nhis_payment.extract([sample.page(cells, size=size)])
    assert result.form_kind == "government_payment"
    assert result.structure_complete is False
    assert any(not v.passed for v in result.validations)
    assert result.warnings
    assert all(field.confidence <= .4 for field in result.fields.values())


def test_text_layer_uses_same_form_geometry_without_ocr_correction():
    cells, size = sample.payment()
    page, words = sample.page(cells, size=size)
    page.source = PageSource.TEXT_LAYER
    words.engine = "text_layer"
    result = nhis_payment.extract([(page, words)])
    assert result.structure_complete
    cells, size = sample.payment(corrected=True)
    page, words = sample.page(cells, size=size)
    page.source = PageSource.TEXT_LAYER
    words.engine = "text_layer"
    result = nhis_payment.extract([(page, words)])
    assert result.structure_complete is False
    assert "숫자형식교정" not in result.fields


def test_payment_preserves_workplace_text_without_numeric_correction():
    result = extraction(workplace="가상 OIl 사업장", corrected=True)
    assert result.structure_complete
    assert result.fields["사업장명칭"].value == "가상 OIl 사업장"
    assert "가입구분" not in result.fields


@pytest.mark.parametrize("label", ["가입자 성명", "생년월일", "납부자번호", "용도구분", "2026 년 03 월 03 일"])
def test_payment_fragmented_label_and_issue_words_keep_value_cells(label):
    cells, size = sample.payment()
    selected = next(cell for cell in cells if cell[4] == label)
    cells.remove(selected)
    x0, y0, x1, y1, text, confidence = selected
    fragments = text.split() if " " in text else list(text)
    step = (x1 - x0) / len(fragments)
    for index, fragment in enumerate(fragments):
        cells.append(sample.cell(x0 + step * index, y0, x0 + step * (index + .8), y1, fragment, confidence))
    result = nhis_payment.extract([sample.page(cells, size=size)])
    assert result.structure_complete, [validation.name for validation in result.validations if not validation.passed]
    assert result.fields["성명"].value == sample.NAME
    assert result.fields["생년월일"].value == sample.BIRTH
    assert result.fields["발급일"].value == sample.ISSUE


def test_payment_split_money_words_stay_within_observed_column():
    cells, size = sample.payment()
    selected = next(cell for cell in cells if cell[4] == "100,000")
    cells.remove(selected)
    x0, y0, x1, y1, _, confidence = selected
    middle = (x0 + x1) / 2
    cells.extend([sample.cell(x0, y0, middle - 2, y1, "100,", confidence),
                  sample.cell(middle + 2, y0, x1, y1, "000", confidence)])
    result = nhis_payment.extract([sample.page(cells, size=size)])
    assert result.structure_complete
    assert result.fields["건강보험료"].value == "50000"


def test_legacy_three_month_table_with_government_identity_keeps_legacy_contract():
    from engine_v2.tests.test_nhis_extractors import payment_pages, wd

    original = nhis_payment.extract(payment_pages())
    pages = payment_pages()
    pages[0][1].words.extend([wd(10, 20, "문서확인번호:0000-0000-0000-00000", 60),
                              wd(10, 22, "사업장명칭"), wd(30, 22, "가상상사"),
                              wd(60, 22, "납부자번호"), wd(75, 22, "00000000000")])
    result = nhis_payment.extract(pages)
    assert result.form_kind is None
    assert result.structure_complete is None
    assert {key: field.value for key, field in result.fields.items()} == {
        key: field.value for key, field in original.fields.items()}
    assert [(check.name, check.passed) for check in result.validations] == [
        (check.name, check.passed) for check in original.validations]
