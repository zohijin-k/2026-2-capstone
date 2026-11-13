"""Applicant-only projection preserves decisions, officer evidence and reference warnings."""
from copy import deepcopy
from datetime import date

from PIL import Image
import pytest

from demo.backend import models
from demo.backend.api import common, documents, officer
from demo.backend.api.review import document_blockers
from demo.backend.ocr.base import OcrResult
from demo.backend.rules.doc_check import CheckFinding, CheckResult
from demo.backend.rules.doc_types import DocType
from demo.backend.rules.required_docs import DocRequirement
from demo.backend.tests.test_followup3_daily_selection import assess
from demo.backend.tests.test_portal_uploads import client, new_app, upload
from demo.backend.tests.test_verify_upload import (
    assert_safe, authored_image_pdf, authored_recognition, no_db, snapshot,
)
from demo.backend.tools import verify_upload as tool
from engine_v2.tests import fail_case_samples as cases
from engine_v2.tests.followup3_daily_samples import daily_notices


def finding(code, severity="FAIL"):
    return {
        "code": code, "severity": severity, "message": f"가짜 {code} 안내",
        "how_to_fix": "가짜 해결 안내", "link": "", "detail": "담당자 전용 가짜 근거",
    }


def row(findings, status="FAIL"):
    return models.Document(
        application_id=1, slot_key="work_proof", file_path="FAKE.pdf", file_format="pdf",
        doc_type=str(DocType.INSURANCE_4), stage1_status=status, findings_json=findings,
        ocr_json={"fields": {"성명": "가짜성명", "생년월일": "1990-01-01"}},
    )


@pytest.mark.parametrize("status", ["FAIL", "NEEDS_REVIEW", "PASS"])
def test_projection_uses_same_document_findings_not_status_or_code(status):
    source = [
        finding("MISSING_BILLING_MONTHS", "NEEDS_REVIEW"),
        finding("MISSING_BILLING_MONTHS"),
        finding("FAKE_REFERENCE", "INFO"),
        finding("LOW_IMAGE_QUALITY"),
        finding("LOW_OCR_CONFIDENCE", "NEEDS_REVIEW"),
        finding("FAKE_OTHER_TIER", "WARNING"),
    ]
    before = deepcopy(source)
    shown = common.document_dict(row(source, status))
    assert [(f["code"], f["severity"]) for f in shown["findings"]] == [
        ("MISSING_BILLING_MONTHS", "FAIL"), ("FAKE_REFERENCE", "INFO"),
        ("LOW_IMAGE_QUALITY", "FAIL"), ("FAKE_OTHER_TIER", "WARNING"),
    ]
    assert shown["status"] == status
    assert all("detail" not in f for f in shown["findings"])
    assert source == before
    shown["findings"][0]["message"] = "changed response"
    assert source == before


@pytest.mark.parametrize("source", [None, [], [None, "FAKE", 0]])
def test_empty_and_nonfinding_entries_retain_existing_ignored_behavior(source):
    assert common.applicant_findings(source) == []


def test_historical_message_only_failure_hides_review_but_preserves_reference():
    source = [{"message": "가짜 과거 확정 부적합"}, None,
              finding("LOW_OCR_CONFIDENCE", "NEEDS_REVIEW"), finding("FAKE_REFERENCE", "INFO")]
    shown = common.applicant_findings(source)
    assert shown == [source[0], {k: v for k, v in source[-1].items() if k != "detail"}]


def test_review_without_fail_and_other_documents_retain_existing_guidance():
    source = [finding("LOW_OCR_CONFIDENCE", "NEEDS_REVIEW"), finding("FAKE_REFERENCE", "INFO")]
    source[0]["how_to_fix"] = "이대로 제출해도 담당자가 확인합니다."
    review = row(source, "NEEDS_REVIEW")
    failed = row([finding("LOW_IMAGE_QUALITY")])
    assert len(common.document_dict(failed)["findings"]) == 1
    assert common.document_dict(review)["findings"][0]["how_to_fix"] == source[0]["how_to_fix"]
    requirement = DocRequirement("work_proof", DocType.INSURANCE_4, "가짜 서류")
    assert document_blockers([requirement], [review]) == []


def test_hidden_identity_review_cannot_expose_original_name_or_birth():
    source = [finding("LOW_IMAGE_QUALITY"), finding("IDENTITY_MISMATCH", "NEEDS_REVIEW")]
    shown = common.document_dict(row(source))
    assert {f["code"] for f in shown["findings"]} == {"LOW_IMAGE_QUALITY"}
    assert "성명" not in shown["extracted"] and "생년월일" not in shown["extracted"]


@pytest.mark.parametrize("failed", [False, True])
def test_upload_list_final_and_officer_keep_reference_but_hide_only_review(
    client, tmp_path, monkeypatch, failed,
):
    aid = new_app(client)
    path = tmp_path / "FAKE.png"
    Image.new("RGB", (1800, 2400), "white").save(path)
    source = [
        CheckFinding("LOW_OCR_CONFIDENCE", "가짜 담당자 확인 예정", "이대로 제출해도 담당자가 확인합니다.", severity="NEEDS_REVIEW", detail="가짜 내부 경고 근거"),
        CheckFinding("FAKE_REFERENCE", "가짜 체크 표시 미확인 참고", severity="INFO"),
    ]
    if failed:
        source += [CheckFinding("MISSING_ADDRESS_DATES", "가짜 날짜 누락 재발급"),
                   CheckFinding("LOW_IMAGE_QUALITY", "가짜 화질 불량 재업로드")]
    result = CheckResult("FAIL" if failed else "NEEDS_REVIEW", source)
    read = OcrResult(DocType.RESIDENT_ABSTRACT, .4, image_quality=.55 if failed else .9,
                     fields={"발급일": "2026-03-03"}, issue_date=date(2026, 3, 3))
    monkeypatch.setattr(documents, "assess_upload", lambda *a, **kw: (read, result))
    response, _ = upload(client, aid, path, "resident_abstract", filename="FAKE.png")
    expected = [(f.code, f.severity) for f in source if not (failed and f.severity == "NEEDS_REVIEW")]
    assert [(f["code"], f["severity"]) for f in response["findings"]] == expected
    assert response["status"] == result.status
    listed = client.get(f"/api/applications/{aid}/documents").json()
    assert listed[0]["findings"] == response["findings"]
    final = client.get(f"/api/applications/{aid}/final-check").json()
    assert final["documents"][0]["findings"] == response["findings"]
    assert final["documents"][0]["status"] == result.status
    doc_blockers = [b for b in final["blockers"] if b["kind"] == "document" and b["target"] == "resident_abstract"]
    assert bool(doc_blockers) is failed
    if failed:
        assert not final["can_submit"]
        assert source[0].message not in doc_blockers[0]["message"]
        assert all(f.message in doc_blockers[0]["message"] for f in source if f.severity == "FAIL")
        submitted = client.post(f"/api/applications/{aid}/submit")
        assert submitted.status_code == 400
        assert all(f.message in submitted.json()["detail"] for f in source if f.severity == "FAIL")
    else:
        assert response["findings"][0]["how_to_fix"] == source[0].how_to_fix
        assert any("담당자 확인 예정 서류가 1건" in warning for warning in final["warnings"])
    with models.get_session() as session:
        stored = session.get(models.Document, response["document_id"])
        assert stored.findings_json == [f.as_dict() for f in source]
        officer_document = officer._document_view(stored, {})
        assert officer_document["findings"] == stored.findings_json
        # Explicit synthetic historical state only for officer route coverage.
        # This does not turn the rejected applicant submit into a success.
        application = session.get(models.Application, aid)
        application.status = models.STATUS_SUBMITTED
        session.add(application)
        session.commit()
    detail = client.get(f"/api/officer/applications/{aid}")
    assert detail.status_code == 200
    assert detail.json()["documents"][0]["findings"] == [f.as_dict() for f in source]


@pytest.mark.parametrize("partial", [False, True])
def test_daily_unknown_checkbox_reference_metadata_survives_existing_boundary(partial, tmp_path):
    _, read, checked, _ = assess(daily_notices(total=10 if partial else 9))
    assert "참고 정보" in read.fields["판독경고"]
    before = deepcopy(read.fields)
    requirement = DocRequirement("work_proof", DocType.DAILY_WORK_RECORD, "가짜 일용근로")
    document = tool._row(requirement, tmp_path / "FAKE.pdf", read, checked)
    common.document_dict(document)
    assert read.fields == before
    assert document.ocr_json["fields"]["판독경고"] == before["판독경고"]
    assert officer._document_view(document, {})["extracted"]["판독경고"] == before["판독경고"]
    assert checked.status == ("FAIL" if partial else "PASS")
    assert not any(f.severity == "NEEDS_REVIEW" for f in checked.findings)


@pytest.mark.parametrize("case,slot,expected", [
    ("5", "resident_abstract", [("MISSING_ADDRESS_DATES", "FAIL"), ("LOW_IMAGE_QUALITY", "FAIL")]),
    ("7", "nhis_payment", [("MISSING_BILLING_MONTHS", "FAIL")]),
])
def test_source_shaped_case_cli_shows_only_applicant_failures(
    case, slot, expected, tmp_path, monkeypatch, capfd, no_db,
):
    pages = cases.missing_address_dates() if case == "5" else cases.missing_payment_months()
    path = authored_image_pdf(tmp_path / "FAKE-case.pdf", pages)
    authored_recognition(monkeypatch, pages)
    before = snapshot(tmp_path)
    assert tool.main(["--slot", slot, "--self-identity", "--validations", str(path)]) == 0
    captured = capfd.readouterr()
    assert captured.err == ""
    output = captured.out
    assert "reason: LOW_OCR_CONFIDENCE NEEDS_REVIEW\n" in output
    assert [tuple(line.removeprefix("applicant_reason: ").split())
            for line in output.splitlines() if line.startswith("applicant_reason: ")] == expected
    assert "document_status: FAIL\n" in output and "blockers: O\n" in output
    if case == "7":
        assert [line for line in output.splitlines() if line.startswith("failed_validation:")] == [
            "failed_validation: nhis_payment monthly_rows_found",
            "failed_validation: nhis_payment monthly_amounts_numeric",
            "failed_validation: nhis_payment months_continuous",
        ]
    assert_safe(output)
    assert snapshot(tmp_path) == before
