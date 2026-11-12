"""Notification-form adapters preserve the existing NHIS subscriber contract."""
from datetime import date
import json
from types import SimpleNamespace

import pytest

from demo.backend import ocr as chain
from demo.backend.ocr import localocr
from demo.backend.rules.doc_check import check_document
from demo.backend.rules.doc_types import DocType
from demo.backend.rules.identity import Identity
from demo.backend.rules.required_docs import DocRequirement
from engine_v2.extractors import nhis_qualification
from engine_v2.pipeline.preprocess import PageSource
from engine_v2.schemas.models import DocType as V2DocType
from engine_v2.tests.nhis_form_samples import NAME, coordinate_page, qualification_cells, text_pdf


def requirement():
    return DocRequirement(slot_key="nhis_qualification", doc_type=DocType.NHIS_QUALIFICATION,
                          label="가짜 자격확인 통보서", min_issue_date=date(2026, 3, 3))


def converted(cells=None):
    pages = [coordinate_page(qualification_cells() if cells is None else cells)]
    return localocr._from_nhis(nhis_qualification.extract(pages), pages, V2DocType)


def checked(ocr, identity=None, related=None):
    return check_document(requirement(), ocr, date(2026, 3, 3), "pdf",
                          identity or Identity(NAME, date(1990, 1, 1)), related_nhis_docs=related)


def test_matching_subscriber_has_no_identity_warning():
    result = checked(converted())
    assert result.status == "PASS"
    assert result.findings == []


def test_dependent_uses_existing_payment_pair_and_member_rules():
    ocr = converted()
    payment = (str(DocType.NHIS_PAYMENT), {"성명": NAME, "생년월일": "1990-01-01"})
    qualification = (str(DocType.NHIS_QUALIFICATION), ocr.fields)
    dependent = Identity("가짜가족", date(2001, 1, 1))
    paired = checked(ocr, dependent, [payment, qualification])
    assert paired.status == "PASS"
    assert paired.codes == ["NHIS_DEPENDENT_INSURED_PERSON"]
    assert checked(ocr, dependent, [qualification]).status == "NEEDS_REVIEW"
    absent = checked(ocr, Identity("가짜다름", date(2000, 1, 1)), [payment, qualification])
    assert absent.status == "NEEDS_REVIEW"
    assert absent.codes == ["NHIS_SUBSCRIBER_IDENTITY_REVIEW"]


@pytest.mark.parametrize("position", [(42, 72), (49, 55), (27, 51), (29, 32)])
def test_incomplete_notification_reaches_review_before_legacy_subscriber_acceptance(position):
    cells = [cell for cell in qualification_cells() if cell[:2] != position]
    result = converted(cells)
    assert result.confidence < .85
    assert result.fields["양식판독상태"] == "불완전"
    final = checked(result)
    assert final.status == "NEEDS_REVIEW"
    assert final.codes == ["REQUIRED_FIELD_UNREADABLE"]
    assert "가구원목록" not in result.fields and "가구원수" not in result.fields


def test_partial_members_do_not_become_reduced_household_scoring_evidence():
    from demo.backend.rules.facts import build_facts
    cells = [cell for cell in qualification_cells() if cell[:2] != (27, 51)]
    ocr = converted(cells)
    facts = build_facts({}, [{"doc_type": str(DocType.NHIS_QUALIFICATION), "fields": ocr.fields}])
    assert facts.household_size is None
    assert facts.household_size_issue


def test_notification_pdf_and_renamed_expected_values_are_identical(tmp_path, monkeypatch):
    monkeypatch.setenv("ENGINE_V2_OCR", "off")
    source = text_pdf(tmp_path / "fake-alpha.pdf", qualification_cells())
    renamed = tmp_path / "fake-omega.pdf"
    renamed.write_bytes(source.read_bytes())
    results = [chain.read_document(str(path), expected) for path, expected in (
        (source, None), (source, DocType.NHIS_ACQUISITION_LOSS), (renamed, DocType.RESIDENT_ABSTRACT))]
    for ocr in results:
        assert ocr.tier == "localocr" and ocr.engine == "pdftext"
        assert ocr.detected_doc_type == DocType.NHIS_QUALIFICATION
        assert ocr.fields == results[0].fields
        assert ocr.issue_date == date(2026, 3, 3)
        assert checked(ocr).status == "PASS"
        assert "0-0000-20260301-000000" not in json.dumps(ocr.fields)
        assert "2026-04-03" not in json.dumps(ocr.fields)
        assert ocr.fields["자격확인요청일"] == "2026-03-01"


def test_generic_qualification_pdf_stays_on_legacy_pdftext(tmp_path, monkeypatch):
    monkeypatch.setenv("ENGINE_V2_OCR", "off")
    cells = [(10, 10, "건강보험 자격확인서"), (10, 20, "성명 : 가짜이름"),
             (10, 25, "발급일 : 2026.03.03"), (10, 30, "가구원수 : 2")]
    ocr = chain.read_document(str(text_pdf(tmp_path / "fake-generic.pdf", cells)))
    assert ocr.tier == "pdftext"
    assert ocr.fields["가구원수"] == "2"
    assert "양식판독상태" not in ocr.fields


def test_known_notification_with_missing_form_cue_does_not_fall_back_to_pdftext(tmp_path, monkeypatch):
    monkeypatch.setenv("ENGINE_V2_OCR", "off")
    cells = [cell for cell in qualification_cells() if cell[2] != "자 격 확 인 내 역"]
    ocr = chain.read_document(str(text_pdf(tmp_path / "fake-malformed.pdf", cells)))
    assert ocr.tier == "localocr"
    assert ocr.fields["양식판독상태"] == "불완전"
    assert checked(ocr).status == "NEEDS_REVIEW"


def test_mocked_image_notification_uses_the_same_coordinate_extractor(tmp_path, monkeypatch):
    from PIL import Image
    from dataclasses import replace
    page, words = coordinate_page(qualification_cells())
    page = replace(page, source=PageSource.UPLOAD, png=b"synthetic")
    original = list(localocr._import_v2())
    original[3] = lambda *args: words
    original[5] = lambda *args: [page]
    monkeypatch.setattr(localocr, "_import_v2", lambda: tuple(original))
    monkeypatch.setattr(localocr, "_merge_image_heuristics", lambda *args: None)
    monkeypatch.setenv("ENGINE_V2_OCR", "fake")
    path = tmp_path / "fake-image.png"
    Image.new("RGB", (1000, 1400), "white").save(path)
    ocr = chain.read_document(str(path), DocType.RESIDENT_ABSTRACT)
    assert ocr.tier == "localocr"
    assert ocr.detected_doc_type == DocType.NHIS_QUALIFICATION
    assert ocr.fields == {**converted().fields,
        "원본이미지크기": '[{"page":0,"width":1000,"height":1400}]'}
    assert checked(ocr).status == "PASS"


def test_final_safety_filter_cannot_leave_notification_name_missing_but_passed(monkeypatch):
    ocr = converted()
    ocr.fields["성명"] = "주 민 등 록 번 호"
    monkeypatch.setattr(chain, "CHAIN", [SimpleNamespace(read=lambda *_: ocr)])
    final = chain.read_document("fake-unused.pdf")
    assert "성명" not in final.fields
    assert "성명_required" in final.fields["판독검증실패"]
    assert final.confidence < .85
    assert checked(final).status == "NEEDS_REVIEW"


def test_member_text_on_marker_row_is_reviewed_instead_of_silently_dropped():
    cells = [(x, y, "가짜누락" if x == 10 and y == 55 else
              "020202-3******" if x == 27 and y == 55 else text)
             for x, y, text in qualification_cells()]
    ocr = converted(cells)
    assert "가구원목록" not in ocr.fields and "가구원수" not in ocr.fields
    assert ocr.fields["양식판독상태"] == "불완전"
    assert checked(ocr).status == "NEEDS_REVIEW"
