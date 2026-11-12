"""Synthetic fixtures retain the supplied shape without storing source contents."""
from engine_v2.tests import fail_case_samples as sample
from demo.backend.ocr.pdftext import classify_pages_with_evidence


def test_daily_split_words_and_duplicate_copy_shape():
    pages = sample.daily()
    assert len(pages) == 4
    assert "근로복지공단이사장" in pages[1][1].text
    assert any(word.text == "1,2,3," for word in pages[0][1].words)
    assert len(pages[0][1].words) == len(pages[2][1].words)


def test_address_fixture_has_date_headers_but_no_date_values():
    page, result = sample.missing_address_dates()[0]
    assert page.pixel_size == (970, 1282)
    assert "신 고 일" in result.text and "발  생일" in result.text
    assert sum(word.text == "전입" for word in result.words) == 3


def test_tiny_fixture_keeps_independent_marker_but_unknown_title():
    pages = sample.tiny_unknown()
    assert pages[0][0].pixel_size == (586, 709)
    assert "1/2" in pages[0][1].text
    assert classify_pages_with_evidence(pages)[0] is None


def test_password_pdf_is_actually_encrypted(tmp_path):
    import pymupdf
    with pymupdf.open(sample.encrypted_pdf(tmp_path / "FAKE.pdf")) as doc:
        assert doc.needs_pass
