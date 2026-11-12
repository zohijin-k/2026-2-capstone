"""Fictitious payment omissions need independent printed date/table evidence."""
import json
from datetime import date, timedelta

import pytest

from demo.backend.ocr import read_document
from demo.backend.ocr.base import OcrResult
from demo.backend.ocr.localocr import _from_nhis
from demo.backend.rules.doc_check import check_document
from demo.backend.rules.doc_types import DocType
from demo.backend.rules.required_docs import DocRequirement
from engine_v2.extractors import nhis_payment
from engine_v2.extractors.payment_period import FIELD
from engine_v2.schemas.models import DocType as V2DocType
from engine_v2.tests import fail_case_samples, p2_payment_samples as sample


MONTHS = ["2025-10", "2025-11", "2025-12"]


def requirement(kind=DocType.NHIS_PAYMENT):
    return DocRequirement(slot_key="nhis_payment" if kind == DocType.NHIS_PAYMENT else "resident_abstract",
                          doc_type=kind, label="가짜 서류", min_issue_date=date(2026, 3, 3),
                          premium_months=MONTHS if kind == DocType.NHIS_PAYMENT else [])


def convert(pages):
    return _from_nhis(nhis_payment.extract(pages), pages, V2DocType)


def result(pages):
    return check_document(requirement(), convert(pages))


def payment(cells=None):
    original, size = sample.payment()
    return [sample.page(original if cells is None else cells, size=size)]


def test_actual_password_pdf_remains_failure_at_zero_confidence(tmp_path, monkeypatch):
    monkeypatch.setenv("ENGINE_V2_OCR", "off")
    path = fail_case_samples.encrypted_pdf(tmp_path / "FAKE-encrypted.pdf")
    read = read_document(str(path), DocType.NHIS_PAYMENT)
    assert read.is_encrypted and read.confidence == 0
    checked = check_document(requirement(), read)
    assert checked.status == "FAIL"
    finding = next(item for item in checked.findings if item.code == "UNREADABLE_FILE")
    assert finding.severity == "FAIL"
    assert finding.how_to_fix == "PDF 암호를 해제한 뒤 다시 올려 주세요. 발급처에서 '암호 설정 안 함'으로 재발급받는 것이 가장 확실합니다."


def test_preannouncement_issue_date_still_fails_and_cutoff_is_inclusive():
    for offset, expected in [(-1, "FAIL"), (0, "PASS")]:
        issue = date(2026, 3, 3) + timedelta(days=offset)
        read = OcrResult(detected_doc_type=DocType.RESIDENT_ABSTRACT, confidence=.95,
                         issue_date=issue, fields={"발급일": issue.isoformat()}, tier="fixture")
        checked = check_document(requirement(DocType.RESIDENT_ABSTRACT), read)
        assert checked.status == expected
        assert ("DOCUMENT_ISSUED_TOO_EARLY" in checked.codes) is (offset < 0)


def test_no_month_map_short_period_is_certain_despite_unrelated_confidence_cap():
    read = convert(fail_case_samples.missing_payment_months())
    assert "월별고지금액" not in read.fields
    assert read.confidence <= .4
    assert json.loads(read.fields[FIELD])["status"] == "READABLE"
    checked = check_document(requirement(), read)
    assert checked.status == "FAIL"
    assert next(item for item in checked.findings if item.code == "MISSING_BILLING_MONTHS").severity == "FAIL"


def test_normal_period_and_annual_zero_placeholders_remain_pass():
    read = convert(payment())
    evidence = json.loads(read.fields[FIELD])
    assert evidence["period"] == ["2025-10", "2025-12"]
    assert evidence["status"] == "READABLE"
    assert evidence["amounts_certain"] is True
    assert result(payment()).status == "PASS"


@pytest.mark.parametrize("defect", ["missing", "low-confidence", "invalid-month", "conflicting-query", "positive-outside", "explicit-outside"])
def test_uncertain_or_conflicting_periods_do_not_reject(defect):
    cells, _ = sample.payment()
    if defect == "missing":
        cells = [cell for cell in cells if "납부내역" not in cell[4]]
    elif defect == "low-confidence":
        cells = [(*cell[:5], .5) if "납부내역" in cell[4] else cell for cell in cells]
    elif defect == "invalid-month":
        cells = [(*cell[:4], "2025년 99월 ~ 2025년 12월 납부내역", cell[5]) if "납부내역" in cell[4] else cell for cell in cells]
    elif defect == "conflicting-query":
        cells.append(sample.cell(500, 710, 1300, 750, "조회기간 2024년 01월 ~ 2024년 09월", 1))
    elif defect == "positive-outside":
        cells = [(*cell[:4], "12345", 1) if cell[4] == "0" and cell[0] < 500 and cell[1] == 962 else cell for cell in cells]
    else:
        cells = [(*cell[:4], "2024-01", 1) if cell[4] == "1월" else cell for cell in cells]
    checked = result(payment(cells))
    assert checked.status == "NEEDS_REVIEW"
    assert all(item.severity != "FAIL" for item in checked.findings)


def zero_or_blank_cells(blank=False):
    cells, _ = sample.payment()
    authored = []
    for cell in cells:
        x0,y0,x1,y1,text,confidence = cell
        health_column = 300 < x0 < 500 or 1100 < x0 < 1300
        if y0 == 1493 and health_column:  # Printed October health cell.
            if blank:
                continue
            text = "0"
        elif y0 == 1726 and health_column:
            text = "50,000"
        elif x0 == 738 and y0 == 1799:
            text = "65,000"
        authored.append((x0,y0,x1,y1,text,confidence))
    return authored


@pytest.mark.parametrize("blank", [False, True])
def test_zero_or_observed_blank_target_amount_rejects_only_with_table_arithmetic(blank):
    pages = payment(zero_or_blank_cells(blank))
    read = convert(pages)
    evidence = json.loads(read.fields[FIELD])
    assert evidence["amounts_certain"] is True
    assert "2025-10" in evidence["absent_amount_months"]
    checked = check_document(requirement(), read)
    assert checked.status == "FAIL"
    assert "MISSING_BILLING_MONTHS" in checked.codes


@pytest.mark.parametrize("defect", ["header", "sum", "grand-total", "unknown-value"])
def test_zero_or_blank_without_complete_column_arithmetic_stays_review(defect):
    cells = zero_or_blank_cells(True)
    if defect == "header":
        cells = [cell for cell in cells if cell[4] != "고지금액"]
    elif defect == "sum":
        cells = [(*cell[:4], "50,001", cell[5]) if cell[1] == 1726 and 300 < cell[0] < 500 else cell for cell in cells]
    elif defect == "grand-total":
        cells = [(*cell[:4], "65,001", cell[5]) if cell[0] == 738 else cell for cell in cells]
    else:
        cells = [(*cell[:4], "FAKE", cell[5]) if cell[4] == "20,000" and cell[0] < 500 else cell for cell in cells]
    checked = result(payment(cells))
    assert checked.status == "NEEDS_REVIEW"
    assert all(item.severity != "FAIL" for item in checked.findings)


@pytest.mark.parametrize("map_value", [None, "{}", "not-json", '{"2025-10":"123"}'])
def test_historical_missing_or_corrupt_map_without_printed_period_is_review(map_value):
    fields = {"월별고지금액": map_value} if map_value is not None else {}
    read = OcrResult(detected_doc_type=DocType.NHIS_PAYMENT, confidence=.95, fields=fields, tier="fixture")
    checked = check_document(requirement(), read)
    assert checked.status == "NEEDS_REVIEW"
    assert checked.codes == ["MISSING_BILLING_MONTHS"]
