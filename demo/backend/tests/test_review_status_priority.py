"""Clearly fictitious stored applications preserve every independent failure."""
from datetime import datetime, timedelta
import json

import pytest
from sqlmodel import select

from demo.backend import models
from demo.backend.api.review import _link_overlapping_households, _run_review
from demo.backend.rules.doc_types import DocType
from demo.backend.rules.programs import DOUBLE_SAVINGS, PROGRAMS
from demo.backend.tests.test_income_review import isolated_db, make_application
from demo.backend.tests.test_portal_uploads import client


ACTIONS = {"PASS": "자동 승인", "FAIL": "반려/보완요청 안내", "NEEDS_REVIEW": "담당자 재검토 필요"}


def assert_status(review, final, stage2):
    assert review.final_status == review.review_payload_json["final_status"] == final
    assert review.stage2_status == stage2
    assert review.review_payload_json["recommended_action"] == ACTIONS[final]


def alter_document(app, doc_type, change):
    with models.get_session() as session:
        document = session.exec(select(models.Document).where(
            models.Document.application_id == app.id, models.Document.doc_type == str(doc_type))).one()
        change(document)
        session.add(document)
        session.commit()


@pytest.mark.parametrize("case,final,stage1,stage2,expected_codes", [
    ("age-and-income", "FAIL", "PASS", "FAIL", {"AGE_OUT_OF_RANGE", "INCOME_UNDETERMINED"}),
    ("region-and-household", "FAIL", "PASS", "FAIL",
     {"NOT_TARGET_REGION", "HEALTH_INSURANCE_HOUSEHOLD_SIZE_UNCONFIRMED", "INCOME_UNDETERMINED"}),
    ("document-and-income", "FAIL", "FAIL", "NEEDS_REVIEW", {"MISSING_REQUIRED_DOC", "INCOME_UNDETERMINED"}),
    ("income-only", "NEEDS_REVIEW", "PASS", "NEEDS_REVIEW", {"INCOME_UNDETERMINED"}),
    ("age-only", "FAIL", "PASS", "FAIL", {"AGE_OUT_OF_RANGE"}),
    ("all-pass", "PASS", "PASS", "PASS", set()),
])
def test_real_pipeline_merges_independent_results_and_keeps_reasons(
        isolated_db, case, final, stage1, stage2, expected_codes):
    app = make_application(premium=0, payment_problem={
        "age-and-income": "missing-month", "region-and-household": "no-household",
        "document-and-income": "missing-month", "income-only": "missing-month",
    }.get(case))
    if case in {"age-and-income", "age-only"}:
        birth = (PROGRAMS[DOUBLE_SAVINGS].birth_range[0] - timedelta(days=1)).isoformat()
        app.form1_json = {**app.form1_json, "birth": birth}
        app.identity_json = {**app.identity_json, "birth": birth}
    if case == "region-and-household":
        app.form1_json = {**app.form1_json, "address": "가상 비대상 지역 0"}
    if case == "document-and-income":
        with models.get_session() as session:
            required = session.exec(select(models.Document).where(
                models.Document.application_id == app.id,
                models.Document.doc_type == str(DocType.RESIDENT_ABSTRACT))).one()
            session.delete(required)
            session.commit()
    review = _run_review(app)
    assert_status(review, final, stage2)
    assert review.stage1_status == stage1
    codes = {row["code"] for row in review.review_payload_json["reasons"]}
    assert expected_codes <= codes
    if case == "all-pass":
        assert not codes
    if case == "document-and-income":
        assert all(row["stage"] == "stage1_document" for row in review.review_payload_json["reasons"]
                   if row["code"] == "MISSING_REQUIRED_DOC")


def store_submitted(app, review, number):
    app.application_no = number
    app.status = models.STATUS_SUBMITTED
    with models.get_session() as session:
        session.add(app)
        session.add(review)
        session.commit()
        session.refresh(review)
        session.refresh(app)


def assert_officer_views(client, application_id, final, stage2):
    listing = client.get("/api/officer/applications", params={"role": "province"})
    assert listing.status_code == 200
    row = next(row for row in listing.json()["rows"] if row["application_id"] == application_id)
    detail = client.get(f"/api/officer/applications/{application_id}", params={"role": "province"})
    assert detail.status_code == 200
    ai = detail.json()["ai"]
    assert row["ai_status"] == ai["final_status"] == final
    assert ai["stage2_status"] == stage2
    assert ai["recommended_action"] == ACTIONS[final]
    return detail.json()


@pytest.mark.parametrize("previous_failure", ["none", "stage1", "stage2"])
@pytest.mark.parametrize("current_failure", [False, True])
def test_overlap_preserves_both_reviews_and_reopens_officer_decision(
        client, previous_failure, current_failure):
    previous = make_application(premium=0)
    old_review = _run_review(previous)
    if previous_failure != "none":
        old_review.final_status = "FAIL"
        old_review.stage1_status = "FAIL" if previous_failure == "stage1" else "PASS"
        old_review.stage2_status = "FAIL" if previous_failure == "stage2" else "PASS"
        old_review.review_payload_json = {"final_status": "FAIL", "recommended_action": ACTIONS["FAIL"],
                                         "reasons": [{"code": "FAKE_EXISTING_FAILURE", "message": "가상 확정 실패"}]}
    old_review.officer_role = "province"
    old_review.officer_decision = "reject" if previous_failure != "none" else "approve"
    old_review.officer_memo = "가상 담당자 메모"
    old_review.decided_at = datetime(2026, 6, 1)
    store_submitted(previous, old_review, "FAKE-PREVIOUS-000")
    current = make_application(premium=0, payment_problem="missing-month")
    if current_failure:
        current.form1_json = {**current.form1_json, "address": "가상 비대상 지역 0"}
    members = [{"성명": "가상공통가구원", "생년월일": "2001-01-01"}]

    def put_members(document):
        raw = document.ocr_json
        document.ocr_json = {**raw, "fields": {**raw["fields"], "가구원목록": json.dumps(members)}}

    for application in (previous, current):
        alter_document(application, DocType.NHIS_QUALIFICATION, put_members)
    current_review = _run_review(current)
    _link_overlapping_households(current, current_review)
    # Repeat discovery to check that reason/link deduplication keeps every other reason.
    _link_overlapping_households(current, current_review)
    current_status = "FAIL" if current_failure else "NEEDS_REVIEW"
    assert_status(current_review, current_status, current_status)
    store_submitted(current, current_review, "FAKE-CURRENT-000")
    previous_status = "NEEDS_REVIEW" if previous_failure == "none" else "FAIL"
    previous_stage2 = "FAIL" if previous_failure == "stage2" else "NEEDS_REVIEW"
    with models.get_session() as session:
        saved = session.get(models.Review, old_review.id)
        assert_status(saved, previous_status, previous_stage2)
        assert session.get(models.Application, previous.id).status == models.STATUS_REVIEWING
        assert saved.stage1_status == old_review.stage1_status
        assert saved.officer_role is saved.officer_decision is saved.officer_memo is saved.decided_at is None
        for review in (saved, current_review):
            payload = review.review_payload_json
            assert len(payload["related_applications"]) == len(payload["household_overlap_details"]) == 1
            codes = [row["code"] for row in payload["reasons"]]
            assert codes.count("HEALTH_INSURANCE_HOUSEHOLD_OVERLAP") == 1
        if previous_failure != "none":
            assert saved.review_payload_json["reasons"][0]["code"] == "FAKE_EXISTING_FAILURE"
        assert "INCOME_UNDETERMINED" in {row["code"] for row in current_review.review_payload_json["reasons"]}
    assert_officer_views(client, previous.id, previous_status, previous_stage2)
    assert_officer_views(client, current.id, current_status, current_status)


@pytest.mark.parametrize("problem,expected", [(None, "PASS"), ("missing-month", "NEEDS_REVIEW")])
def test_new_review_list_detail_and_payload_agree(client, problem, expected):
    app = make_application(premium=0, payment_problem=problem)
    review = _run_review(app)
    assert_status(review, expected, expected)
    store_submitted(app, review, "FAKE-VIEWS-000")
    assert_officer_views(client, app.id, expected, expected)
