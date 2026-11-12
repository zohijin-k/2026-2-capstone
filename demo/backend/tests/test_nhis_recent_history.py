"""Fictitious uploads and old JSON exercise the coverage/verdict boundary."""
from datetime import date
import json

import pytest

from demo.backend.ocr import read_document
from demo.backend.ocr.base import OcrResult
from demo.backend.rules.doc_check import check_document
from demo.backend.rules.doc_types import DocType
from demo.backend.rules.identity import Identity
from demo.backend.tests.test_nhis_form import requirement
from demo.backend.tests.test_p2_nhis_uploads import image_pdf, use_own_words
from demo.backend.tests.test_portal_uploads import client, new_app
from engine_v2.tests.nhis_form_samples import NAME, BIRTH, text_pdf
from engine_v2.tests.nhis_recent_history_samples import ISSUE, cells_for, own_cells


@pytest.mark.parametrize("mode", ["text", "own-image"])
@pytest.mark.parametrize("case,status,code,covered,basis", [
    ("complete", "PASS", None, True, "full_history"),
    ("old", "PASS", None, True, "history_rows"),
    ("full-period", "PASS", None, True, "query_period"),
    ("missing-marker", "NEEDS_REVIEW", "REQUIRED_FIELD_UNREADABLE", None, "undetermined"),
    ("bad-structure", "NEEDS_REVIEW", "REQUIRED_FIELD_UNREADABLE", None, "undetermined"),
    ("short-period", "FAIL", "NHIS_HISTORY_PERIOD_MISSING", False, "query_period"),
    ("unreadable-period", "NEEDS_REVIEW", "NHIS_HISTORY_PERIOD_UNREADABLE", None, "undetermined"),
])
def test_actual_upload_preserves_three_states_and_applicant_guidance(
        client, tmp_path, monkeypatch, mode, case, status, code, covered, basis):
    cells = cells_for(case)
    if mode == "text":
        path = text_pdf(tmp_path / "FAKE-unrelated.pdf", cells)
    else:
        use_own_words(monkeypatch, own_cells(cells), (2000, 2800))
        path = image_pdf(tmp_path / "FAKE-unrelated.pdf", (2000, 2800))
    direct = read_document(str(path))
    assert direct.detected_doc_type == DocType.NHIS_ACQUISITION_LOSS
    history = json.loads(direct.fields["자격이력자료"])
    assert history["recent_five_years_covered"] is covered
    assert history["coverage_basis"] == basis
    result = check_document(requirement(), direct, identity=Identity(NAME, date.fromisoformat(BIRTH)))
    assert result.status == status
    assert result.codes == ([code] if code else [])
    # Use no declared issue date: upload helper's fixed date belongs to its
    # earlier fixture, whereas this explicitly authored document is from 2031.
    aid = new_app(client)
    response = client.post(f"/api/applications/{aid}/documents",
        files={"file": ("FAKE-renamed.pdf", path.read_bytes(), "application/pdf")},
        data={"slot_key": "nhis_acquisition_loss"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == status
    assert [finding["code"] for finding in body["findings"]] == ([code] if code else [])
    from demo.backend import models
    with models.get_session() as session:
        stored = session.get(models.Document, body["document_id"]).ocr_json
        assert stored["fields"] == direct.fields
        assert stored["engine"] == ("own" if mode == "own-image" else "pdftext")
    guidance = " ".join(f.how_to_fix for f in result.findings)
    if case == "short-period":
        assert "다시 발급" in guidance
        assert result.findings[0].severity == "FAIL"
    else:
        assert "다시 발급" not in guidance
        assert "재발급" not in guidance
        assert all(f.severity != "FAIL" for f in result.findings)
    if case == "complete":
        assert history["period"] is None
        assert history["rows"][0]["lost"] is None
        assert len(history["rows"]) == 2
        assert direct.confidence >= .85
        assert direct.fields["양식판독상태"] == "완전"
        assert not direct.fields.get("판독검증실패")


def checked(data, *, confidence=.95, quality=.9, years=5):
    req = requirement()
    req.recent_years = years
    ocr = OcrResult(detected_doc_type=DocType.NHIS_ACQUISITION_LOSS, confidence=confidence,
        image_quality=quality, issue_date=date.fromisoformat(ISSUE), tier="pdftext",
        fields={"성명": NAME, "생년월일": BIRTH, "발급일": ISSUE, "양식판독상태": "완전",
                "자격이력자료": json.dumps(data, ensure_ascii=False)})
    return check_document(req, ocr, identity=Identity(NAME, date.fromisoformat(BIRTH)))


@pytest.mark.parametrize("boolean", ["absent", True, False])
@pytest.mark.parametrize("old", [True, False])
@pytest.mark.parametrize("empty_period", [None, [], ""])
def test_legacy_json_positive_results_preserved_and_uncertain_negatives_reviewed(boolean, old, empty_period):
    data = {"period": empty_period, "rows": [
        {"acquired": "2000-01-01" if old else "2028-01-01",
         "lost": "2010-01-01" if old else "2029-01-01"}]}
    if boolean != "absent":
        data["recent_five_years_covered"] = boolean
    previously_passed = boolean is True or (boolean == "absent" and old)
    result = checked(data)
    assert result.status == ("PASS" if previously_passed else "NEEDS_REVIEW")
    if not previously_passed:
        assert result.codes == ["NHIS_HISTORY_PERIOD_MISSING"]
        assert all(f.severity == "NEEDS_REVIEW" for f in result.findings)
        assert all("발급" not in f.how_to_fix for f in result.findings)


@pytest.mark.parametrize("data", [
    [], None, "FAKE-unreadable", {"rows": [None]},
    {"coverage_basis": "undetermined", "recent_five_years_covered": None},
    {"coverage_basis": "history_rows", "recent_five_years_covered": None,
     "rows": [{"acquired": "2000-01-01", "lost": "2010-01-01"}]},
    {"coverage_basis": "FAKE-unknown", "recent_five_years_covered": True},
    {"coverage_basis": "query_period", "recent_five_years_covered": False, "period": None},
    {"coverage_basis": "full_history", "recent_five_years_covered": True,
     "period_label_present": True},
    {"coverage_basis": "history_rows", "recent_five_years_covered": False,
     "period_label_present": False, "rows": []},
    {"period": ["2031-07-08", "2020-01-01"]},
])
def test_missing_or_contradictory_evidence_is_review_without_reissuance(data):
    result = checked(data)
    assert result.status == "NEEDS_REVIEW"
    assert result.codes == ["NHIS_HISTORY_PERIOD_UNREADABLE"]
    assert all(f.severity == "NEEDS_REVIEW" and "발급" not in f.how_to_fix for f in result.findings)


@pytest.mark.parametrize("confidence,quality", [(.5, .9), (.95, .4), (.95, .9)])
def test_short_explicit_period_is_fail_only_when_readable(confidence, quality):
    data = {"period": ["2028-01-01", ISSUE], "rows": [],
            "coverage_basis": "query_period", "recent_five_years_covered": False}
    result = checked(data, confidence=confidence, quality=quality)
    certain = confidence >= .85 and quality >= .6
    assert result.status == ("FAIL" if certain else "NEEDS_REVIEW")
    finding = next(f for f in result.findings if f.code == "NHIS_HISTORY_PERIOD_MISSING")
    assert finding.severity == ("FAIL" if certain else "NEEDS_REVIEW")
    assert ("다시 발급" in finding.how_to_fix) is certain


@pytest.mark.parametrize("years,status", [(5, "PASS"), (20, "NEEDS_REVIEW")])
def test_row_evidence_is_recomputed_for_requested_years(years, status):
    data = {"period": None, "coverage_basis": "history_rows", "period_label_present": False,
            "coverage_years": 5, "recent_five_years_covered": True,
            "rows": [{"acquired": "2010-01-01", "lost": "2020-01-01"}]}
    assert checked(data, years=years).status == status
