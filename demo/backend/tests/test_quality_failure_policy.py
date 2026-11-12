"""Only measured low source quality rejects; certainty and OCR review stay separate."""
from datetime import date
import json

from PIL import Image
import pytest

from demo.backend import upload_assessment
from demo.backend.api.review import document_blockers
from demo.backend.ocr.base import OcrResult
from demo.backend.rules.doc_check import (check_document, QUALITY_REUPLOAD_GUIDANCE,
                                           REVIEW_ONLY_CODES, CODE_SCREEN_CAPTURE)
from demo.backend.rules.doc_types import DocType
from demo.backend.rules.required_docs import DocRequirement
from demo.backend.tests.test_address_resolution_failures import convert, req
from demo.backend.tests.test_daily_work_uploads import text_pdf
from demo.backend.tests.test_p2_resident_uploads import use_own_words
from demo.backend.tests.test_portal_uploads import client, new_app, upload
from demo.backend.tests.test_verify_upload import assert_safe, no_db, snapshot
from demo.backend.tools import verify_upload as tool
from engine_v2.tests.followup3_daily_samples import daily_notices
from engine_v2.tests.followup_address_samples import sparse_dates


def plain_req():
    return DocRequirement("work_proof", DocType.FARM_BIZ_CERT, "가짜 서류")


@pytest.mark.parametrize("confidence", [0, .4, 1])
@pytest.mark.parametrize("path", ["normal", "unknown", "daily-incomplete", "nhis-incomplete"])
def test_quality_fail_survives_confidence_and_every_early_return(confidence, path):
    kind = {"normal": DocType.FARM_BIZ_CERT, "unknown": None,
            "daily-incomplete": DocType.DAILY_WORK_RECORD,
            "nhis-incomplete": DocType.NHIS_ACQUISITION_LOSS}[path]
    fields = {"양식판독상태": "불완전"} if "incomplete" in path else {}
    read = OcrResult(kind, confidence, image_quality=.55, fields=fields, tier="localocr")
    result = check_document(DocRequirement("work_proof", kind or DocType.FARM_BIZ_CERT, "가짜 서류"),
                            read, file_format="jpg")
    assert result.status == "FAIL"
    found = [f for f in result.findings if f.code == "LOW_IMAGE_QUALITY"]
    assert len(found) == 1 and found[0].severity == "FAIL"
    assert found[0].how_to_fix == QUALITY_REUPLOAD_GUIDANCE
    assert "이대로 제출해도" not in found[0].how_to_fix


def test_only_quality_leaves_review_only_vocabulary():
    assert "LOW_IMAGE_QUALITY" not in REVIEW_ONLY_CODES
    for code in ("LOW_OCR_CONFIDENCE", CODE_SCREEN_CAPTURE, "IDENTITY_UNCERTAIN",
                 "REQUIRED_FIELD_UNREADABLE", "PAGES_UNREADABLE"):
        assert code in REVIEW_ONLY_CODES
    result = check_document(plain_req(), OcrResult(DocType.FARM_BIZ_CERT, .1, image_quality=.9))
    assert result.status == "NEEDS_REVIEW"
    assert result.codes == ["LOW_OCR_CONFIDENCE"]
    assert all(f.severity == "NEEDS_REVIEW" for f in result.findings)


def test_nhis_identity_review_cannot_downgrade_measured_quality():
    from demo.backend.rules.identity import Identity
    read = OcrResult(DocType.NHIS_ACQUISITION_LOSS, .4, image_quality=.5,
                     fields={"성명": "가짜이름", "생년월일": "1990-01-01", "발급일": "2026-03-03"},
                     issue_date=date(2026,3,3), tier="localocr")
    result = check_document(DocRequirement("nhis_acquisition_loss", DocType.NHIS_ACQUISITION_LOSS, "가짜 서류"),
                            read, identity=Identity("다른가짜명", date(1991,1,1)))
    assert "IDENTITY_UNCERTAIN" in result.codes
    assert next(f.severity for f in result.findings if f.code == "LOW_IMAGE_QUALITY") == "FAIL"
    assert result.status == "FAIL"


def test_specific_date_page_and_quality_failures_all_reach_one_blocker(tmp_path):
    read = convert(sparse_dates())
    read.confidence = .95  # Independent readable folios, despite measured poor resolution.
    read.fields["쪽표기자료"] = json.dumps({"markers": [[1,2]], "confidence": .99})
    result = check_document(req(), read, file_format="jpg")
    required = {"MISSING_ADDRESS_DATES", "PAGES_INCOMPLETE", "LOW_IMAGE_QUALITY"}
    failures = [f for f in result.findings if f.severity == "FAIL"]
    assert required <= {f.code for f in failures}
    row = tool._row(req(), tmp_path / "FAKE.jpg", read, result)
    row.findings_json.insert(0, {"code": "LOW_OCR_CONFIDENCE", "severity": "NEEDS_REVIEW", "message": "가짜 검토 전용 경고"})
    row.findings_json.append(dict(row.findings_json[-1]))
    blocker = document_blockers([req()], [row])[0]
    for finding in failures:
        assert finding.message in blocker["message"]
        assert blocker["message"].count(finding.message) == 1
    assert "가짜 검토 전용 경고" not in blocker["message"]


@pytest.mark.parametrize("size", [(970,1282), (586,709), (1654,2338)])
def test_receipt_ocr_absence_retains_quality_specific_failure_only_when_measured(size, tmp_path):
    path = tmp_path / "FAKE.png"
    Image.new("RGB", size, "white").save(path)
    from demo.backend.ocr.file_evidence import normalize_image_quality, attach_file_evidence
    read = OcrResult(None, 0, image_quality=1, tier="none")
    attach_file_evidence(read, str(path))
    normalize_image_quality(read, str(path))
    requirement = DocRequirement("exam_receipt", DocType.PAYMENT_RECEIPT, "가짜 영수증")
    _, result = upload_assessment.assess_upload(path, requirement, reader=lambda *_: read)
    assert "RECEIPT_OCR_UNAVAILABLE" in result.codes
    if size[0] == 1654:
        assert result.status == "NEEDS_REVIEW"
        assert not any(f.severity == "FAIL" for f in result.findings)
    else:
        assert result.status == "FAIL"
        expected = "IMAGE_RESOLUTION_TOO_LOW" if size[0] == 586 else "LOW_IMAGE_QUALITY"
        assert next(f.severity for f in result.findings if f.code == expected) == "FAIL"
        assert not ("LOW_IMAGE_QUALITY" in result.codes and "IMAGE_RESOLUTION_TOO_LOW" in result.codes)


@pytest.mark.parametrize("partial", [False, True])
def test_source_daily_pdf_cli_preserves_selection_and_work_results(partial, tmp_path, monkeypatch, capfd, no_db):
    path = text_pdf(tmp_path / "FAKE-opaque.pdf", daily_notices(total=10 if partial else 9))
    monkeypatch.setenv("ENGINE_V2_OCR", "off")
    before = snapshot(tmp_path)
    assert tool.main(["--slot", "work_proof", "--work-category", "지역가입자·피부양자",
                      "--self-identity", str(path)]) == 0
    output = capfd.readouterr()
    assert output.err == ""
    assert "blockers: O\n" in output.out and "identity: O\n" in output.out
    assert f"document_status: {'FAIL' if partial else 'PASS'}\n" in output.out
    assert f"work_status: {'UNDETERMINED' if partial else 'NOT_MET'}\n" in output.out
    assert "reason: LOW_IMAGE_QUALITY" not in output.out
    if partial:
        assert "reason: DAILY_RECORDS_PARTIALLY_SELECTED FAIL\n" in output.out
    assert_safe(output.out)
    assert snapshot(tmp_path) == before


def test_actual_synthetic_image_upload_and_final_check_show_both_failures(client, tmp_path, monkeypatch):
    pages = sparse_dates()
    use_own_words(monkeypatch, pages)
    path = tmp_path / "FAKE.png"
    Image.new("RGB", pages[0][0].pixel_size, "white").save(path)
    aid = new_app(client)
    response, stored = upload(client, aid, path, "resident_abstract", filename="FAKE.png")
    failures = [f for f in response["findings"] if f["severity"] == "FAIL"]
    assert response["status"] == "FAIL"
    assert {"LOW_IMAGE_QUALITY", "MISSING_ADDRESS_DATES"} <= {f["code"] for f in failures}
    final = client.get(f"/api/applications/{aid}/final-check").json()
    blocker = next(b for b in final["blockers"] if b["kind"] == "document" and b["target"] == "resident_abstract")
    assert not final["can_submit"]
    assert all(f["message"] in blocker["message"] for f in failures)
    submitted = client.post(f"/api/applications/{aid}/submit")
    assert submitted.status_code == 400
    assert all(f["message"] in submitted.json()["detail"] for f in failures)
