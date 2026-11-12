"""Actual image-PDF uploads feed fictitious own-OCR words through the demo API."""
import io
from datetime import date

import pymupdf
import pytest
from PIL import Image

from demo.backend.ocr import read_document
from demo.backend.ocr.localocr import LocalOcr, _from_nhis
from demo.backend.rules.doc_check import check_document
from demo.backend.rules.doc_types import DocType
from demo.backend.rules.identity import Identity
from demo.backend.tests.test_nhis_form import requirement
from demo.backend.tests.test_portal_uploads import client, new_app, upload
from engine_v2.extractors import nhis_acquisition_loss
from engine_v2.pipeline import ocr as coordinate_ocr
from engine_v2.schemas.models import DocType as V2DocType
from engine_v2.tests import p2_form_samples as sample


def image_pdf(path, size):
    content = io.BytesIO()
    Image.new("RGB", size, "white").save(content, format="PNG")
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_image(page.rect, stream=content.getvalue())
        document.save(path)
    return path


def use_own_words(monkeypatch, cells, size):
    import demo.backend.ocr as chain

    monkeypatch.setenv("ENGINE_V2_OCR", "own")
    monkeypatch.setattr(chain, "CHAIN", [LocalOcr()])

    def recognize(png, actual_size):
        assert png
        assert actual_size == size
        return sample.page(cells, size=size)[1].words

    monkeypatch.setitem(coordinate_ocr.ENGINES, "own", recognize)


@pytest.mark.parametrize("full_rrn", [False, True])
def test_own_acquisition_upload_preserves_birth_and_matches_identity_without_warnings(
        client, tmp_path, monkeypatch, full_rrn):
    cells, size = sample.acquisition(full_rrn=full_rrn)
    use_own_words(monkeypatch, cells, size)
    path = image_pdf(tmp_path / "FAKE-own-acquisition.pdf", size)
    direct = read_document(str(path), DocType.NHIS_QUALIFICATION)
    assert direct.detected_doc_type == DocType.NHIS_ACQUISITION_LOSS
    assert direct.fields["생년월일"] == sample.BIRTH
    assert direct.fields["양식판독상태"] == "완전"
    assert not direct.fields.get("판독검증실패")
    aid = new_app(client, name=sample.NAME, birth=sample.BIRTH)
    response, stored = upload(client, aid, path, "nhis_acquisition_loss")
    assert response["status"] == "PASS"
    assert response["findings"] == []
    assert stored["fields"] == direct.fields
    assert stored["engine"] == "own"
    assert "123456" not in str(stored)


@pytest.mark.parametrize("defect", ["overlap", "missing-date", "hidden-row", "wrong-identity"])
def test_own_acquisition_upload_reviews_uncertain_or_overlapping_history(
        client, tmp_path, monkeypatch, defect):
    cells, size = sample.acquisition(overlap=defect == "overlap")
    if defect == "missing-date":
        cells = [cell for cell in cells if not (cell[0] == 1652 and cell[1] == 1243)]
    elif defect == "hidden-row":
        cells.append(sample.cell(845, 2100, 1105, 2150, "가상사업장", .99))
    use_own_words(monkeypatch, cells, size)
    path = image_pdf(tmp_path / "FAKE-own-incomplete.pdf", size)
    name = "가상다름" if defect == "wrong-identity" else sample.NAME
    response, stored = upload(client, new_app(client, name=name, birth=sample.BIRTH),
                              path, "nhis_acquisition_loss")
    assert response["status"] == "NEEDS_REVIEW"
    assert response["findings"]
    assert all(finding["severity"] != "FAIL" for finding in response["findings"])
    if defect != "wrong-identity":
        assert stored["fields"]["양식판독상태"] == "불완전"
        assert stored["confidence"] <= .4


@pytest.mark.parametrize("overlap", [False, True])
def test_acquisition_direct_verdict_agrees_with_structure_checks(overlap):
    cells, size = sample.acquisition(overlap=overlap)
    pages = [sample.page(cells, size=size)]
    extraction = nhis_acquisition_loss.extract(pages)
    result = _from_nhis(extraction, pages, V2DocType)
    verdict = check_document(requirement(), result, identity=Identity(sample.NAME, date(1990, 1, 1)))
    assert verdict.status == ("NEEDS_REVIEW" if overlap else "PASS")
    assert all(finding.severity != "FAIL" for finding in verdict.findings)
    if not overlap:
        assert verdict.findings == []
