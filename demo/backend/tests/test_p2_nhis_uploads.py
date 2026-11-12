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
from demo.backend.tests.test_nhis_qualification import requirement as qualification_requirement
from demo.backend.tests.test_portal_uploads import client, new_app, upload
from engine_v2.extractors import nhis_acquisition_loss, nhis_qualification
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


@pytest.mark.parametrize("same_dates", [False, True])
def test_own_qualification_upload_with_one_member_has_no_identity_warning(
        client, tmp_path, monkeypatch, same_dates):
    cells, size = sample.qualification(same_dates=same_dates)
    use_own_words(monkeypatch, cells, size)
    path = image_pdf(tmp_path / "FAKE-own-qualification.pdf", size)
    direct = read_document(str(path), DocType.NHIS_ACQUISITION_LOSS)
    assert direct.detected_doc_type == DocType.NHIS_QUALIFICATION
    assert direct.fields["가구원수"] == "1"
    assert direct.fields["양식판독상태"] == "완전"
    assert not direct.fields.get("판독검증실패")
    aid = new_app(client, name=sample.NAME, birth=sample.BIRTH)
    response, stored = upload(client, aid, path, "nhis_qualification")
    assert response["status"] == "PASS"
    assert response["findings"] == []
    assert stored["fields"] == direct.fields
    assert stored["engine"] == "own"


@pytest.mark.parametrize("defect", ["missing-member-birth", "duplicate-issue", "malformed-issue",
                                  "hidden-member", "wrong-identity"])
def test_own_qualification_upload_reviews_partial_members_or_ambiguous_issue(
        client, tmp_path, monkeypatch, defect):
    cells, size = sample.qualification()
    if defect == "missing-member-birth":
        cells = [cell for cell in cells if not (cell[0] == 413 and cell[1] == 1493)]
    elif defect in {"duplicate-issue", "malformed-issue"}:
        text = "2026.03.03" if defect == "duplicate-issue" else "2026.99.99"
        cells.append(sample.cell(1114, 2830, 1375, 2893, text, 1))
    elif defect == "hidden-member":
        cells.append(sample.cell(155, 2100, 375, 2155, "가상누락", .99))
    use_own_words(monkeypatch, cells, size)
    path = image_pdf(tmp_path / "FAKE-own-incomplete-qualification.pdf", size)
    name = "가상다름" if defect == "wrong-identity" else sample.NAME
    response, stored = upload(client, new_app(client, name=name, birth=sample.BIRTH),
                              path, "nhis_qualification")
    assert response["status"] == "NEEDS_REVIEW"
    assert response["findings"]
    assert all(finding["severity"] != "FAIL" for finding in response["findings"])
    if defect != "wrong-identity":
        assert stored["fields"]["양식판독상태"] == "불완전"
        assert "가구원목록" not in stored["fields"]
        assert "가구원수" not in stored["fields"]


def test_qualification_direct_verdict_preserves_single_matching_subscriber():
    cells, size = sample.qualification()
    pages = [sample.page(cells, size=size)]
    result = _from_nhis(nhis_qualification.extract(pages), pages, V2DocType)
    verdict = check_document(qualification_requirement(), result,
                             identity=Identity(sample.NAME, date(1990, 1, 1)))
    assert verdict.status == "PASS"
    assert verdict.findings == []
