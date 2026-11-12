"""Fictitious NHIS identity checks across extraction and final result safety."""
from datetime import date
from types import SimpleNamespace
import pytest

from demo.backend import ocr as chain
from demo.backend.ocr.base import OcrResult
from demo.backend.ocr.localocr import _from_nhis
from demo.backend.rules.doc_check import check_document
from demo.backend.rules.doc_types import DocType
from demo.backend.rules.identity import Identity
from demo.backend.rules.required_docs import DocRequirement
from engine_v2.extractors import nhis_acquisition_loss
from engine_v2.schemas.models import DocType as V2DocType
from engine_v2.tests.nhis_form_samples import NAME, BIRTH, ISSUE, coordinate_page, text_pdf


def requirement():
    return DocRequirement(slot_key="nhis_acquisition_loss", doc_type=DocType.NHIS_ACQUISITION_LOSS,
                          label="가짜 자격득실 확인서", min_issue_date=date(2026, 3, 3), recent_years=5)


def checked(result, identity=None):
    return check_document(requirement(), result, date(2026, 3, 3), "pdf",
                          identity or Identity(NAME, date(1990, 1, 1)))


def test_actual_pdf_missing_name_cannot_keep_all_passed_validation_or_pass(tmp_path, monkeypatch):
    monkeypatch.setenv("ENGINE_V2_OCR", "off")
    result = chain.read_document(str(text_pdf(tmp_path / "fake-missing.pdf", name=None)))
    assert "성명" not in result.fields
    assert result.fields.get("판독검증실패")
    assert result.confidence < .85
    assert checked(result).status == "NEEDS_REVIEW"


def test_actual_pdf_identity_below_headers_passes_with_matching_applicant(tmp_path, monkeypatch):
    monkeypatch.setenv("ENGINE_V2_OCR", "off")
    result = chain.read_document(str(text_pdf(tmp_path / "fake-normal.pdf")))
    assert result.fields["성명"] == NAME
    assert result.fields["생년월일"] == BIRTH
    assert result.issue_date == date.fromisoformat(ISSUE)
    assert checked(result).status == "PASS"
    assert not checked(result).findings


@pytest.mark.parametrize("missing", ["성명", "생년월일", "발급일"])
def test_conversion_records_missing_required_fields_as_failed_validation(missing):
    pages = [coordinate_page()]
    extracted = nhis_acquisition_loss.extract(pages)
    extracted.fields.pop(missing, None)
    converted = _from_nhis(extracted, pages, V2DocType)
    assert missing in converted.fields["판독검증실패"]
    assert converted.confidence < .85
    assert checked(converted).status == "NEEDS_REVIEW"


@pytest.mark.parametrize("missing", ["성명", "생년월일", "발급일"])
def test_final_header_filter_cannot_leave_false_success(missing, monkeypatch):
    fields = {"성명": NAME, "생년월일": BIRTH, "발급일": ISSUE, "판독검증": "8/8 통과"}
    fields[missing] = "주 민 등 록 번 호" if missing == "성명" else missing
    result = OcrResult(detected_doc_type=DocType.NHIS_ACQUISITION_LOSS, confidence=.95,
                       image_quality=.9, issue_date=date(2026, 3, 3), fields=fields, tier="localocr")
    monkeypatch.setattr(chain, "CHAIN", [SimpleNamespace(read=lambda *_: result)])
    final = chain.read_document("unused-fake.pdf")
    assert missing not in final.fields
    assert missing in final.fields["판독검증실패"]
    assert final.confidence < .85
    assert checked(final).status == "NEEDS_REVIEW"


@pytest.mark.parametrize("fields", [
    {"성명": "가짜다름", "생년월일": BIRTH, "발급일": ISSUE},
    {"성명": NAME, "생년월일": "1991-01-01", "발급일": ISSUE},
    {"생년월일": BIRTH, "발급일": ISSUE},
    {"성명": NAME, "발급일": ISSUE},
])
def test_acquisition_missing_or_mismatching_identity_is_review_not_fail(fields):
    result = OcrResult(detected_doc_type=DocType.NHIS_ACQUISITION_LOSS, confidence=.95,
                       image_quality=.9, issue_date=date(2026, 3, 3), fields=fields, tier="localocr")
    check = checked(result)
    assert check.status == "NEEDS_REVIEW"
    assert all(f.severity != "FAIL" for f in check.findings)


def test_mismatching_identity_does_not_reject_on_other_persons_history():
    import json
    fields = {"성명": "가짜다름", "생년월일": BIRTH, "발급일": ISSUE,
              "자격이력자료": json.dumps({"period": None, "rows": [],
                                          "recent_five_years_covered": False})}
    result = OcrResult(detected_doc_type=DocType.NHIS_ACQUISITION_LOSS, confidence=.95,
                       image_quality=.9, issue_date=date(2026, 3, 3), fields=fields, tier="localocr")
    check = checked(result)
    assert "NHIS_HISTORY_PERIOD_MISSING" in check.codes
    assert check.status == "NEEDS_REVIEW"
    assert all(f.severity != "FAIL" for f in check.findings)
