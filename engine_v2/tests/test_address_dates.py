"""Certain omitted dates versus unreadable layout, using fictitious coordinate rows."""
import pytest
from engine_v2.extractors.address_dates import assess
from engine_v2.pipeline.ocr import OcrWord
from engine_v2.tests.fail_case_samples import missing_address_dates
from engine_v2.tests import p2_resident_samples


def test_present_date_columns_empty_rows_are_certain_omission():
    evidence = assess(missing_address_dates(), type_confidence=.95)
    assert evidence["status"] == "MISSING"
    assert evidence["pages"][0]["reason"] == "rows_without_dates"
    assert evidence["pages"][0]["rows"] == 3


def test_missing_date_column_labels_but_observed_address_header():
    pages = missing_address_dates()
    pages[0][1].words[:] = [w for w in pages[0][1].words if w.text not in {"발  생일", "신 고 일"}]
    assert assess(pages, type_confidence=.95)["pages"][0]["reason"] == "date_headers_absent"


@pytest.mark.parametrize("defect", ["header", "type", "row", "date-damage", "low-row-confidence"])
def test_broken_certainty_stays_undetermined(defect):
    pages = missing_address_dates(header=defect != "header")
    if defect == "row":
        pages[0][1].words[:] = [w for w in pages[0][1].words if not w.text.isdigit()]
    elif defect == "date-damage":
        pages[0][1].words.append(OcrWord("2025-??-??", .95, (530,470,620,490)))
    elif defect == "low-row-confidence":
        for word in pages[0][1].words:
            if word.text.isdigit():
                word.confidence = .4
    assert assess(pages, type_confidence=.4 if defect == "type" else .95)["status"] == "UNDETERMINED"


def test_existing_complete_multisheet_document_never_becomes_omission():
    assert assess(p2_resident_samples.resident(), type_confidence=.95)["status"] != "MISSING"
