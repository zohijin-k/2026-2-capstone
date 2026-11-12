"""Confirmed structural ambiguities must remain reviewable after extraction."""
import pytest

from engine_v2.extractors import nhis_acquisition_loss, nhis_payment
from engine_v2.tests.nhis_form_samples import acquisition_cells, coordinate_page
from engine_v2.tests import p2_payment_samples as sample


@pytest.mark.parametrize("corrupt", ["2025.OI.OI", "OOOO.OI.OI"])
def test_oversized_employer_cannot_absorb_malformed_loss_date(corrupt):
    cells = [(x, y, "가상상사" * 17 if x == 33 and y == 37 else text)
             for x, y, text in acquisition_cells()]
    cells.append((81, 37, corrupt))
    result = nhis_acquisition_loss.extract([coordinate_page(cells)])
    assert not result.structure_complete
    assert not next(check.passed for check in result.validations if check.name == "nhis_history_cells_read")
    assert all(field.confidence <= .4 for field in result.fields.values())


@pytest.mark.parametrize("kind", ["crossing-name", "crossing-money", "crossing-payer", "period-conflict",
                                "same-period", "malformed-period", "document-residue", "split-document-residue"])
def test_payment_metadata_requires_complete_unambiguous_cells(kind):
    cells, size = sample.payment()
    if kind in {"crossing-name", "crossing-money"}:
        text = "가상다름" if kind == "crossing-name" else "1,000,000"
        cells.append(sample.cell(1100, 509, 1250, 560, text, 1))
    elif kind == "crossing-payer":
        cells.append(sample.cell(1250, 590, 1350, 634, "12345678901", 1))
    elif kind in {"period-conflict", "same-period", "malformed-period"}:
        text = {"period-conflict": "2024년 01월 ~ 2024년 12월 납부내역",
                "same-period": "2025년 10월 ~ 2025년 12월 납부내역",
                "malformed-period": "2025년 OO월 ~ 2025년 12월 납부내역"}[kind]
        cells.append(sample.cell(757, 705, 1310, 746, text, 1))
    elif kind == "document-residue":
        cells = [(*cell[:4], cell[4] + "가상추가" if "문서확인번호" in cell[4] else cell[4], cell[5]) for cell in cells]
    else:
        cells.append(sample.cell(1100, 98, 1250, 138, "가상추가", 1))
    result = nhis_payment.extract([sample.page(cells, size=size)])
    assert result.form_kind == "government_payment"
    assert not result.structure_complete
    assert any(not check.passed for check in result.validations)
    assert all(field.confidence <= .4 for field in result.fields.values())


def test_single_period_can_share_its_row_with_unit_annotation():
    cells, size = sample.payment()
    cells = [cell for cell in cells if cell[4] != "(단위:원)"]
    cells.append(sample.cell(1450, 660, 1600, 701, "(단위:원)", 1))
    assert nhis_payment.extract([sample.page(cells, size=size)]).structure_complete


def test_document_number_scope_ignores_authenticity_stamp_to_the_left():
    cells, size = sample.payment()
    cells.append(sample.cell(61, 57, 170, 172, "가상", .76))
    cells.append(sample.cell(170, 50, 289, 172, "도장", .68))
    assert nhis_payment.extract([sample.page(cells, size=size)]).structure_complete


@pytest.mark.parametrize("field", ["purpose", "workplace"])
@pytest.mark.parametrize("header", ["성명", "보험료"])
def test_payment_header_only_text_cannot_replace_a_required_or_explicit_blank_value(field, header):
    cells, size = sample.payment(workplace=header if field == "workplace" else "")
    if field == "purpose":
        cells = [(*cell[:4], header if cell[4] == "납부확인용" else cell[4], cell[5]) for cell in cells]
    result = nhis_payment.extract([sample.page(cells, size=size)])
    assert not result.structure_complete
    assert any(not check.passed for check in result.validations)
