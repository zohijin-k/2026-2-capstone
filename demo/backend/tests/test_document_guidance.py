"""Format-specific guidance must preserve every sentence except the photo fragment."""
from datetime import date

import pytest

from demo.backend.ocr.base import OcrResult
from demo.backend.rules.doc_check import (
    PHOTO_RETAKE_GUIDANCE, RETAKE_GUIDANCE, check_document,
)
from demo.backend.rules.doc_types import DocType
from demo.backend.rules.required_docs import DocRequirement


def requirement(kind=DocType.NHIS_QUALIFICATION):
    return DocRequirement(slot_key="FAKE-slot", doc_type=kind, label="가짜 서류",
                          min_issue_date=date(2026, 3, 3))


@pytest.mark.parametrize("file_format", ["pdf", "PDF", "jpg", "png"])
def test_unknown_document_early_return_uses_file_specific_guidance(file_format):
    result = check_document(requirement(), OcrResult(detected_doc_type=None, confidence=0,
                            image_quality=.9, fields={}, tier="pdftext"), file_format=file_format)
    assert result.status == "NEEDS_REVIEW"
    guidance = result.findings[0].how_to_fix
    if file_format.lower() == "pdf":
        assert guidance == RETAKE_GUIDANCE.replace(PHOTO_RETAKE_GUIDANCE, "")
        assert "흐리거나" not in guidance
    else:
        assert guidance == RETAKE_GUIDANCE


@pytest.mark.parametrize("kind", [DocType.NHIS_ACQUISITION_LOSS, DocType.NHIS_QUALIFICATION, DocType.INSURANCE_4])
def test_incomplete_portal_early_return_never_adds_photo_fragment_to_pdf(kind):
    read = OcrResult(detected_doc_type=kind, confidence=.4, image_quality=.9,
                     fields={"양식판독상태": "불완전"}, tier="localocr")
    result = check_document(requirement(kind), read, file_format="pdf")
    assert result.status == "NEEDS_REVIEW"
    for finding in result.findings:
        assert PHOTO_RETAKE_GUIDANCE not in finding.message
        assert PHOTO_RETAKE_GUIDANCE not in finding.how_to_fix
        assert "이대로 제출해도 담당자가 확인합니다." in finding.how_to_fix


def test_pdf_changes_only_the_designated_fragment_on_normal_rule_path():
    read = OcrResult(detected_doc_type=DocType.NHIS_QUALIFICATION, confidence=.5,
                     image_quality=.9, fields={}, tier="pdftext")
    pdf = check_document(requirement(), read, file_format="pdf")
    photo = check_document(requirement(), read, file_format="jpg")
    assert pdf.status == photo.status == "NEEDS_REVIEW"
    assert pdf.findings and len(pdf.findings) == len(photo.findings)
    for actual, original in zip(pdf.findings, photo.findings):
        expected = original.as_dict()
        for key in ("message", "how_to_fix"):
            expected[key] = expected[key].replace(PHOTO_RETAKE_GUIDANCE, "")
        assert actual.as_dict() == expected
