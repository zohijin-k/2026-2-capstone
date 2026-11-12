"""Sparse-header reproduction now reaches the independent omission failure."""
from demo.backend.tests.test_address_resolution_failures import convert, req
from demo.backend.rules.doc_check import check_document
from engine_v2.tests.followup_address_samples import sparse_dates


def test_sparse_header_proves_date_omission_despite_quality_review():
    read = convert(sparse_dates())
    result = check_document(req(), read, file_format="jpg")
    assert read.confidence == .4
    assert result.status == "FAIL"
    assert "LOW_IMAGE_QUALITY" in result.codes
    assert "MISSING_ADDRESS_DATES" in result.codes
    assert next(f.severity for f in result.findings if f.code == "MISSING_ADDRESS_DATES") == "FAIL"
