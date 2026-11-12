"""Pre-fix observation on authored sparse-header geometry, with no identity output."""
from demo.backend.tests.test_address_resolution_failures import convert, req
from demo.backend.rules.doc_check import check_document
from engine_v2.tests.followup_address_samples import sparse_dates


def test_sparse_header_reproduces_review_without_date_omission():
    read = convert(sparse_dates())
    result = check_document(req(), read, file_format="jpg")
    assert read.confidence == .4
    assert result.status == "NEEDS_REVIEW"
    assert "LOW_IMAGE_QUALITY" in result.codes
    assert "MISSING_ADDRESS_DATES" not in result.codes
