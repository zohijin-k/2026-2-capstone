"""Actual resident image-PDF uploads preserve note numbering and review gaps."""
import io

import pymupdf
import pytest
from PIL import Image

from demo.backend.ocr import read_document
from demo.backend.ocr.localocr import LocalOcr
from demo.backend.rules.doc_types import DocType
from demo.backend.tests.test_portal_uploads import client, new_app, upload
from engine_v2.pipeline import ocr as coordinate_ocr
from engine_v2.tests import p2_resident_samples as sample


def image_pdf(path, pages):
    content = io.BytesIO()
    Image.new("RGB", pages[0][0].pixel_size, "white").save(content, format="PNG")
    with pymupdf.open() as document:
        for _ in pages:
            page = document.new_page()
            page.insert_image(page.rect, stream=content.getvalue())
        document.save(path)
    return path


def use_own_words(monkeypatch, pages):
    import demo.backend.ocr as chain

    monkeypatch.setenv("ENGINE_V2_OCR", "own")
    monkeypatch.setattr(chain, "CHAIN", [LocalOcr()])
    captured = iter(pages)

    def recognize(png, size):
        page, result = next(captured)
        assert png
        assert size == page.pixel_size
        return result.words

    monkeypatch.setitem(coordinate_ocr.ENGINES, "own", recognize)


@pytest.mark.parametrize("boundary", [False, True])
def test_resident_note_false_alarm_is_fixed_in_actual_upload(client, tmp_path, monkeypatch, boundary):
    pages = sample.resident(boundary=boundary)
    use_own_words(monkeypatch, pages)
    path = image_pdf(tmp_path / "FAKE-resident-notes.pdf", pages)
    direct = read_document(str(path), DocType.NHIS_PAYMENT)
    assert direct.detected_doc_type == DocType.RESIDENT_ABSTRACT
    assert direct.confidence >= .9
    assert not direct.fields.get("판독검증실패")
    assert not direct.fields.get("판독경고")
    use_own_words(monkeypatch, sample.resident(boundary=boundary))
    response, stored = upload(client, new_app(client, name=sample.NAME, birth=sample.BIRTH), path, "resident_abstract")
    assert response["status"] == "PASS"
    assert response["findings"] == []
    assert stored["fields"] == direct.fields
    assert stored["fields"]["성명"] == sample.NAME
    assert stored["fields"]["생년월일"] == sample.BIRTH


@pytest.mark.parametrize("defect", ["first", "last", "all", "middle", "note", "duplicate", "unreadable"])
def test_resident_remaining_number_uncertainty_reaches_upload_review(client, tmp_path, monkeypatch, defect):
    pages = sample.damage(sample.resident(), defect)
    use_own_words(monkeypatch, pages)
    path = image_pdf(tmp_path / "FAKE-resident-missing-number.pdf", pages)
    response, stored = upload(client, new_app(client, name=sample.NAME, birth=sample.BIRTH), path, "resident_abstract")
    assert response["status"] == "NEEDS_REVIEW"
    assert response["findings"]
    assert all(finding["severity"] != "FAIL" for finding in response["findings"])
    assert stored["confidence"] <= .4
    assert "history_numbers_sequential" in stored["fields"]["판독검증실패"]
    assert stored["fields"]["판독경고"]
    assert stored["fields"]["성명"] == sample.NAME
    assert stored["fields"]["생년월일"] == sample.BIRTH
