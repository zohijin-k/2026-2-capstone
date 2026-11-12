"""Payment own-OCR words traverse actual image-PDF upload and persistence."""
import json

import pymupdf
import pytest

from demo.backend.ocr import read_document
from demo.backend.rules.doc_types import DocType
from demo.backend.tests.test_p2_nhis_uploads import image_pdf, use_own_words
from demo.backend.tests.test_portal_uploads import client, new_app, upload
from engine_v2.tests import p2_payment_samples as sample


@pytest.mark.parametrize("corrected", [False, True])
@pytest.mark.parametrize("optional", [False, True])
def test_payment_upload_matches_identity_and_persists_all_corrections(
        client, tmp_path, monkeypatch, corrected, optional):
    cells, size = sample.payment(corrected=corrected, optional=optional)
    use_own_words(monkeypatch, cells, size)
    path = image_pdf(tmp_path / "FAKE-payment.pdf", size)
    direct = read_document(str(path), DocType.RESIDENT_ABSTRACT)
    assert direct.detected_doc_type == DocType.NHIS_PAYMENT
    assert direct.fields["양식판독상태"] == "완전"
    assert not direct.fields.get("판독검증실패")
    assert not direct.fields.get("판독경고")
    response, stored = upload(client, new_app(client, name=sample.NAME, birth=sample.BIRTH), path, "nhis_payment")
    assert response["status"] == "PASS"
    assert response["findings"] == []
    assert stored["fields"] == direct.fields
    assert stored["engine"] == "own"
    assert stored["fields"]["건강보험료"] == "50000"
    assert "가입구분" not in stored["fields"]
    if corrected:
        corrections = json.loads(stored["fields"]["숫자형식교정"])
        assert any(item["row"] == "10월" and item["column"] == 1 and
                   item["categories"] == ["digit_lookalike", "group_separator"] for item in corrections)
    else:
        assert "숫자형식교정" not in stored["fields"]


@pytest.mark.parametrize("defect", ["arithmetic", "unknown-glyph", "missing-name", "missing-birth", "wrong-identity",
                                  "missing-header", "missing-month", "grand-total"])
def test_payment_upload_keeps_uncertain_numbers_and_partial_identity_in_review(
        client, tmp_path, monkeypatch, defect):
    cells, size = sample.payment(corrected=True)
    if defect in {"arithmetic", "unknown-glyph"}:
        replacement = "I00.001" if defect == "arithmetic" else "A"
        cells = [(*cell[:4], replacement, cell[5]) if cell[4] == "I00.000" else cell for cell in cells]
    elif defect in {"missing-name", "missing-birth", "missing-header", "missing-month"}:
        text = {"missing-name": sample.NAME, "missing-birth": "1990.01.01.", "missing-header": "고지금액", "missing-month": "4월"}[defect]
        cells = [cell for cell in cells if cell[4] != text]
    elif defect == "grand-total":
        cells = [(*cell[:4], "165,001", cell[5]) if cell[0] == 738 else cell for cell in cells]
    use_own_words(monkeypatch, cells, size)
    path = image_pdf(tmp_path / "FAKE-payment-incomplete.pdf", size)
    name = "가상다름" if defect == "wrong-identity" else sample.NAME
    response, stored = upload(client, new_app(client, name=name, birth=sample.BIRTH), path, "nhis_payment")
    assert response["status"] == "NEEDS_REVIEW"
    assert response["findings"]
    assert all(finding["severity"] != "FAIL" for finding in response["findings"])
    if defect != "wrong-identity":
        assert stored["fields"]["양식판독상태"] == "불완전"
        assert stored["fields"]["판독검증실패"]
        assert stored["confidence"] <= .4


def test_payment_text_layer_upload_keeps_same_financial_field_contract(client, tmp_path, monkeypatch):
    cells, size = sample.payment()
    path = tmp_path / "FAKE-payment-text.pdf"
    font = pymupdf.Font("cjk")
    with pymupdf.open() as document:
        page = document.new_page(width=595, height=842)
        for x0, y0, x1, y1, text, _ in cells:
            width = (x1 - x0) / size[0] * 595
            height = (y1 - y0) / size[1] * 842
            fontsize = min(width / font.text_length(text, fontsize=1), height / (font.ascender - font.descender))
            writer = pymupdf.TextWriter(page.rect)
            writer.append((x0 / size[0] * 595, y0 / size[1] * 842 + font.ascender * fontsize),
                          text, font=font, fontsize=fontsize)
            writer.write_text(page)
        document.save(path)
    monkeypatch.setenv("ENGINE_V2_OCR", "off")
    result = read_document(str(path), DocType.RESIDENT_ABSTRACT)
    assert result.engine == "pdftext"
    assert result.fields["양식판독상태"] == "완전"
    assert "숫자형식교정" not in result.fields
    assert result.fields["건강보험료"] == "50000"
    response, stored = upload(client, new_app(client, name=sample.NAME, birth=sample.BIRTH), path, "nhis_payment")
    assert response["status"] == "PASS"
    assert response["findings"] == []
    assert stored["fields"] == result.fields


@pytest.mark.parametrize("missing_headers", [2, 3, 4])
def test_payment_with_multiple_damaged_component_headers_stays_reviewed(
        client, tmp_path, monkeypatch, missing_headers):
    cells, size = sample.payment()
    removed = 0
    remaining = []
    for cell in cells:
        if cell[4] == "소득월액" and removed < missing_headers:
            removed += 1
        else:
            remaining.append(cell)
    use_own_words(monkeypatch, remaining, size)
    path = image_pdf(tmp_path / "FAKE-payment-damaged-headers.pdf", size)
    response, stored = upload(client, new_app(client, name=sample.NAME, birth=sample.BIRTH), path, "nhis_payment")
    assert response["status"] == "NEEDS_REVIEW"
    assert stored["confidence"] <= .4
    assert all(finding["severity"] != "FAIL" for finding in response["findings"])
