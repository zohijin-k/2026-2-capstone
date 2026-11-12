"""Paging cannot override unrelated or fallback OCR uncertainty."""
from dataclasses import replace

import pytest

from demo.backend.rules.doc_check import check_document
from demo.backend.tests.run_p18_applicant_precheck_scenarios import (
    IDENTITY, abstract_slot, read_fake, resident_words,
)


@pytest.mark.parametrize("marker", ["1/2", "1/1"])
@pytest.mark.parametrize("uncertainty", ["external", "fallback", "field", "lower-confidence"])
def test_duplicate_history_does_not_discredit_other_ocr_uncertainty(tmp_path, marker, uncertainty):
    original = read_fake(tmp_path, "uncertain-pages", [resident_words(marker), resident_words(marker)])
    assert original.confidence == .4
    if uncertainty == "external":
        ocr = replace(original, tier="jbai", engine="jbai")
    elif uncertainty == "fallback":
        ocr = replace(original, fallback_reason="가짜 품질 검증 실패")
    elif uncertainty == "field":
        failed = original.fields["판독검증실패"] + ", 성명_consistent"
        ocr = replace(original, fields=dict(original.fields, 판독검증실패=failed))
    else:
        ocr = replace(original, confidence=.3)
    verdict = check_document(abstract_slot(), ocr, identity=IDENTITY)
    assert verdict.status == "NEEDS_REVIEW"
    assert "PAGES_UNREADABLE" in verdict.codes
    assert all(finding.severity != "FAIL" for finding in verdict.findings)
