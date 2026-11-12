"""Fictitious renamed PDFs carry both extracted evidence cells into final review."""
from datetime import date

import pytest
from sqlmodel import select

from demo.backend import models
from demo.backend.api.common import checklist_for
from demo.backend.api.review import _run_review
from demo.backend.ocr import read_document
from demo.backend.rules.doc_check import check_document
from demo.backend.rules.doc_types import DocType
from demo.backend.rules.identity import Identity
from demo.backend.tests.test_income_review import isolated_db, make_application
from engine_v2.tests import p2_form_samples as qualification_sample, p2_payment_samples as payment_sample
from engine_v2.tests.test_income_payment_evidence import _text_pdf


@pytest.mark.parametrize("a,b,expected", [("blank", "blank", "FAIL"), ("present", "present", "PASS"),
                                          ("present", "blank", "NEEDS_REVIEW"),
                                          ("unreadable", "blank", "NEEDS_REVIEW")])
def test_extracted_ab_survives_renaming_validation_storage_and_real_review(isolated_db, tmp_path, monkeypatch, a, b, expected):
    monkeypatch.setenv("ENGINE_V2_OCR", "off")
    app = make_application(premium=0)
    app.form1_json = {**app.form1_json, "name": qualification_sample.NAME, "birth": qualification_sample.BIRTH}
    app.identity_json = {"name": qualification_sample.NAME, "birth": qualification_sample.BIRTH}
    q_cells, q_size = qualification_sample.qualification(noise=False, empty_management=a != "present")
    if a == "unreadable":
        q_cells = [cell for cell in q_cells if cell[4] != "사업장관리번호"]
    p_cells, p_size = payment_sample.payment(workplace="가상사업장" if b == "present" else "")
    requirements = {row.slot_key: row for row in checklist_for(app)}
    identity = Identity(qualification_sample.NAME, date.fromisoformat(qualification_sample.BIRTH))
    with models.get_session() as session:
        for index, (slot, cells, size, wrong_expected) in enumerate((
            ("nhis_qualification", q_cells, q_size, DocType.NHIS_PAYMENT),
            ("nhis_payment", p_cells, p_size, DocType.NHIS_QUALIFICATION),
        )):
            path = _text_pdf(tmp_path / f"FAKE-alpha-{index}.pdf", cells, size)
            renamed = tmp_path / f"FAKE-omega-{index}.pdf"
            renamed.write_bytes(path.read_bytes())
            original = read_document(str(path))
            parsed = read_document(str(renamed), wrong_expected)
            assert parsed.fields == original.fields
            assert parsed.detected_doc_type == requirements[slot].doc_type
            assert parsed.fields["양식판독상태"] == "완전"
            verdict = check_document(requirements[slot], parsed, declared_issue_date=parsed.issue_date,
                                     file_format="pdf", identity=identity)
            assert verdict.status == "PASS"
            stored = session.exec(select(models.Document).where(
                models.Document.application_id == app.id, models.Document.slot_key == slot)).one()
            stored.doc_type = str(parsed.detected_doc_type)
            stored.file_path = str(renamed)
            stored.declared_issue_date = parsed.issue_date
            stored.stage1_status = verdict.status
            stored.ocr_json = {"fields": parsed.fields, "bboxes": parsed.bboxes_as_dict(),
                               "confidence": parsed.confidence, "image_quality": parsed.image_quality,
                               "issue_date": parsed.issue_date.isoformat()}
            session.add(stored)
        session.commit()
    result = _run_review(app)
    assert result.final_status == result.stage2_status == expected
    assert result.review_payload_json["final_status"] == expected
    codes = {reason["code"] for reason in result.review_payload_json["reasons"]}
    assert ("INCOME_OVER_THRESHOLD" in codes) is (expected == "FAIL")
    assert ("INCOME_UNDETERMINED" in codes) is (expected == "NEEDS_REVIEW")
