"""Fictitious applications exercise age ranges, identity locking and final review."""
from datetime import timedelta

import pytest

from demo.backend.api.officer import Entry, _eligibility
from demo.backend.api.review import _run_review
from demo.backend.rules.age_eligibility import assess_age
from demo.backend.rules.programs import DOUBLE_SAVINGS, JOB_PACKAGE, PROGRAMS
from demo.backend.tests.test_income_review import isolated_db, make_application
from demo.backend.tests.test_portal_uploads import client


@pytest.mark.parametrize("program_code", [DOUBLE_SAVINGS, JOB_PACKAGE])
@pytest.mark.parametrize("position,expected,code", [("low", "PASS", None), ("high", "PASS", None),
                                                   ("before", "FAIL", "AGE_OUT_OF_RANGE"),
                                                   ("after", "FAIL", "AGE_OUT_OF_RANGE"),
                                                   ("missing", "NEEDS_REVIEW", "AGE_UNDETERMINED")])
def test_both_programs_enforce_inclusive_range_and_checklist_matches_final_reason(
        isolated_db, program_code, position, expected, code):
    app = make_application(program_code=program_code, premium=0)
    low, high = PROGRAMS[program_code].birth_range
    birth = {"low": low, "high": high, "before": low - timedelta(days=1),
             "after": high + timedelta(days=1)}.get(position)
    app.form1_json = {**app.form1_json, "birth": birth.isoformat() if birth else None}
    if birth:
        app.identity_json = {**app.identity_json, "birth": birth.isoformat()}
    review = _run_review(app)
    assert review.final_status == review.stage2_status == review.review_payload_json["final_status"] == expected
    age = review.review_payload_json["age_eligibility"]
    assert age["status"] == expected
    assert age["reason_code"] == code
    items = {row["key"]: row for row in review.score_json.get("items", [])}
    age_check = next(row for row in _eligibility(Entry(app, review), items) if row["key"] == "age")
    assert age_check["ok"] is (expected == "PASS")
    assert age_check["basis"] == age["basis"]
    reasons = {row["code"]: row for row in review.review_payload_json["reasons"]}
    if code:
        assert reasons[code]["message"] == age_check["basis"]
    if program_code == JOB_PACKAGE:
        assert review.score_json == {}
        assert not any(key.startswith("INCOME") for key in reasons)
        assert (review.supplement_deadline is not None) is (expected != "PASS")


@pytest.mark.parametrize("program_code", [DOUBLE_SAVINGS, JOB_PACKAGE])
@pytest.mark.parametrize("verified", ["1998-01-01", "not-a-date", None, "1999-01-01trailing"])
def test_stored_identity_birth_mismatch_or_malformed_value_requires_review(isolated_db, program_code, verified):
    app = make_application(program_code=program_code, premium=0)
    app.identity_json = {"name": "가상신청", "birth": verified}
    review = _run_review(app)
    assert review.final_status == review.stage2_status == "NEEDS_REVIEW"
    age = review.review_payload_json["age_eligibility"]
    assert age["reason_code"] == "AGE_IDENTITY_MISMATCH"
    check = next(row for row in _eligibility(Entry(app, review), {}) if row["key"] == "age")
    assert not check["ok"]
    assert check["basis"] == age["basis"]


@pytest.mark.parametrize("form_birth", [None, "", "1999-01-01trailing", "1999-99-99", "1999-01-01T00:00:00",
                                         {"y": "1999", "m": "1", "d": ""},
                                         {"y": 1999.5, "m": 1, "d": 1},
                                         {"y": 10**100, "m": 1, "d": 1}])
def test_unreadable_form_birth_never_uses_identity_as_a_passing_fallback(form_birth):
    result = assess_age(PROGRAMS[DOUBLE_SAVINGS], form_birth, {"birth": "1999-01-01"})
    assert result.status == "NEEDS_REVIEW"
    assert result.reason_code == "AGE_UNDETERMINED"
    assert result.birth_date is None


@pytest.mark.parametrize("form_birth", ["1999-01-01", {"y": "1999", "m": "01", "d": "01"},
                                         {"y": 1999, "m": 1, "d": 1}])
def test_existing_birth_formats_and_missing_legacy_identity_remain_supported(form_birth):
    result = assess_age(PROGRAMS[DOUBLE_SAVINGS], form_birth)
    assert result.status == "PASS"
    assert result.reason_code is None
    assert result.as_dict()["birth_date"] == "1999-01-01"


@pytest.mark.parametrize("income,age,expected,age_code", [
    ("unknown", "outside", "NEEDS_REVIEW", "AGE_OUT_OF_RANGE"),
    ("over", "missing", "NEEDS_REVIEW", "AGE_UNDETERMINED"),
    ("over", "mismatch", "NEEDS_REVIEW", "AGE_IDENTITY_MISMATCH"),
    ("met", "outside", "FAIL", "AGE_OUT_OF_RANGE"),
    ("over", "outside", "FAIL", "AGE_OUT_OF_RANGE"),
])
def test_uncertainty_precedes_definite_failure_without_discarding_reason_details(
        isolated_db, income, age, expected, age_code):
    a = b = "못 읽음" if income == "unknown" else "확실한 공란"
    premium = None if income == "unknown" else 999999999 if income == "over" else 0
    app = make_application(a=a, b=b, premium=premium)
    if age == "outside":
        birth = (PROGRAMS[DOUBLE_SAVINGS].birth_range[0] - timedelta(days=1)).isoformat()
        app.form1_json = {**app.form1_json, "birth": birth}
        app.identity_json = {**app.identity_json, "birth": birth}
    elif age == "missing":
        app.form1_json = {**app.form1_json, "birth": None}
    else:
        app.identity_json = {**app.identity_json, "birth": "1998-01-01"}
    review = _run_review(app)
    assert review.final_status == review.stage2_status == review.review_payload_json["final_status"] == expected
    codes = {row["code"] for row in review.review_payload_json["reasons"]}
    assert age_code in codes
    assert ("INCOME_UNDETERMINED" in codes) is (income == "unknown")
    assert ("INCOME_OVER_THRESHOLD" in codes) is (income == "over")


def test_normal_api_keeps_verified_birth_immutable_and_demo_identity_is_one_time(client):
    response = client.post("/api/applications", json={"program_code": DOUBLE_SAVINGS})
    assert response.status_code == 200
    application_id = response.json()["id"]
    body = {"name": "가상신청", "birth": "1999-01-01", "phone": "01000000000", "pledge": True,
            "signature_data_url": "data:image/png;base64,aW52ZW50ZWQtc2lnbmF0dXJl"}
    identity = client.post(f"/api/applications/{application_id}/identity", json=body)
    assert identity.status_code == 200
    assert identity.json()["identity"]["method"] == "demo"
    patch = client.patch(f"/api/applications/{application_id}",
                         json={"form1": {"name": "가상변경", "birth": {"y": "1900", "m": "1", "d": "1"}}})
    assert patch.status_code == 200
    saved = client.get(f"/api/applications/{application_id}").json()
    assert saved["identity_json"]["birth"] == "1999-01-01"
    assert saved["form1_json"]["birth"] == {"y": "1999", "m": "1", "d": "1"}
    assert saved["form1_json"]["name"] == "가상신청"
    assert client.post(f"/api/applications/{application_id}/identity", json={**body, "birth": "1998-01-01"}).status_code == 409


def test_malformed_huge_birth_reaches_review_through_actual_fact_building(isolated_db):
    app = make_application(premium=0)
    app.form1_json = {**app.form1_json, "birth": {"y": 10**100, "m": 1, "d": 1}}
    review = _run_review(app)
    assert review.final_status == review.stage2_status == "NEEDS_REVIEW"
    assert review.review_payload_json["age_eligibility"]["reason_code"] == "AGE_UNDETERMINED"
