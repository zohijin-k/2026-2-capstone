"""Actual uploads keep fictitious resident-number suffixes out of OCR results."""
from dataclasses import asdict
import json

import pymupdf
import pytest

from demo.backend import models
from demo.backend.api import common, officer
from demo.backend.ocr import read_document
from demo.backend.ocr.pdftext import read_page_text
from engine_v2.pipeline import ocr
from engine_v2.tests.nhis_form_samples import acquisition_cells, text_pdf
from .test_portal_uploads import client, new_app, upload


RRN = "900101-1654321"
SUFFIX = "654321"


def privacy_cells(split):
    cells = [(x, y, value) for x, y, value in acquisition_cells() if value != "900101-1******"]
    cells += [(55, 22, "900101-"), (61.5, 22, "1654321")] if split else [(55, 22, RRN)]
    return cells


def image_pdf(source, target):
    with pymupdf.open(source) as original, pymupdf.open() as raster:
        page = raster.new_page(width=595, height=842)
        page.insert_image(page.rect, pixmap=original[0].get_pixmap(matrix=pymupdf.Matrix(4, 4)))
        raster.save(target)
    return target


@pytest.mark.parametrize("image", [False, True])
@pytest.mark.parametrize("split", [False, True])
def test_upload_persisted_results_responses_logs_and_birth(image, split, client, tmp_path, monkeypatch, caplog):
    cells = privacy_cells(split)
    source = text_pdf(tmp_path / "FAKE-privacy-source.pdf", cells)
    path = image_pdf(source, tmp_path / "FAKE-privacy-raster.pdf") if image else source
    observed = []
    if image:
        monkeypatch.setenv("ENGINE_V2_OCR", "own")

        def recognize(_png, size):
            scale_x, scale_y = size[0] / 1000, size[1] / 1400
            words = [ocr.OcrWord(text, .99,
                                 (x * 10 * scale_x, y * 14 * scale_y,
                                  (x + len(text) * .8) * 10 * scale_x, (y + .8) * 14 * scale_y))
                     for x, y, text in cells]
            observed.append(words)
            return words

        monkeypatch.setitem(ocr.ENGINES, "own", recognize)

    aid = new_app(client)
    response, saved = upload(client, aid, path, "nhis_acquisition_loss", filename="FAKE-safe-name.pdf")
    assert saved["fields"]["생년월일"] == "1990-01-01"
    assert response["status"] == "PASS"
    direct = read_document(str(path))
    assert direct.fields["생년월일"] == "1990-01-01"
    with models.get_session() as session:
        row = session.get(models.Document, response["document_id"])
        projections = [row.model_dump(mode="json"), common.document_dict(row),
                       officer._document_view(row, {}), common.document_fact(row)]
    serialized = json.dumps([response, saved, projections, asdict(direct)], ensure_ascii=False, default=str)
    output = tmp_path / "FAKE-saved-result.json"
    output.write_text(serialized, encoding="utf-8")
    assert SUFFIX not in output.read_text(encoding="utf-8")
    assert SUFFIX not in repr(observed)
    assert SUFFIX not in caplog.text


def test_pdftext_masks_raw_text_before_any_parser(monkeypatch):
    from demo.backend.ocr import pdftext

    observed = []
    original = pdftext.classify_with_evidence

    def classify(text):
        observed.append(text)
        return original(text)

    monkeypatch.setattr(pdftext, "classify_with_evidence", classify)
    result = read_page_text("사업자등록증명 주민(법인)등록번호 " + RRN, None, 0)
    assert SUFFIX not in repr(observed)
    assert SUFFIX not in repr(result)


def test_legacy_stored_ocr_values_are_masked_in_read_projections():
    from datetime import datetime

    row = models.Document(id=1, application_id=1, slot_key="FAKE", file_path="storage/FAKE.pdf",
                          file_format="pdf", uploaded_at=datetime(2026, 3, 3),
                          ocr_json={"fields": {"성명": RRN, "주민등록번호": RRN},
                                    "classification_evidence": RRN, "quality_note": RRN},
                          findings_json=[{"code": "FAKE", "message": RRN}])
    views = [common.document_dict(row), common.document_fact(row), officer._document_view(row, {})]
    assert SUFFIX not in repr(views)
    assert row.ocr_json["fields"]["주민등록번호"] == RRN


def test_officer_response_masks_legacy_review_payload_and_score(client):
    aid = new_app(client)
    with models.get_session() as session:
        application = session.get(models.Application, aid)
        application.status = "submitted"
        session.add(application)
        session.add(models.Review(application_id=aid, final_status="NEEDS_REVIEW",
                                  stage1_status="NEEDS_REVIEW",
                                  review_payload_json={"recommended_action": RRN,
                                                       "reasons": [{"message": RRN}]},
                                  score_json={"items": [{"key": "FAKE", "basis": RRN}]}))
        session.commit()
    response = client.get(f"/api/officer/applications/{aid}")
    assert response.status_code == 200
    assert SUFFIX not in response.text
