"""Fictitious stored document facts traverse the real pipeline and review writer."""
from datetime import date, datetime
import json
from types import SimpleNamespace

import pytest
from sqlmodel import create_engine

from demo.backend import models
from demo.backend.api.common import checklist_for
from demo.backend.api.officer import Entry, _eligibility
from demo.backend.api.review import _run_review
from demo.backend.engine_adapter import apply_runtime_overrides, to_engine_applicant
from demo.backend.rules import criteria
from demo.backend.rules.doc_types import DocType
from demo.backend.rules.programs import DOUBLE_SAVINGS, JOB_PACKAGE, PROGRAMS
from demo.backend.rules.scoring import MEDIAN_INCOME_140
from demo.backend.tests.test_income_facts import documents


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    database = create_engine(f"sqlite:///{tmp_path / 'FAKE-income.db'}", connect_args={"check_same_thread": False})
    monkeypatch.setattr(models, "engine", database)
    models.init_db()
    apply_runtime_overrides()
    yield
    database.dispose()


def make_application(*, a="확실한 공란", b="확실한 공란", premium=None, size=1,
                     program_code=DOUBLE_SAVINGS, payment_problem=None):
    premium = MEDIAN_INCOME_140[size if size in MEDIAN_INCOME_140 else 1]["지역"] + 1 if premium is None else premium
    app = models.Application(application_no="FAKE-INCOME-000", program_code=program_code,
                             created_at=datetime(2026, 6, 1),
                             form1_json={"name": "가상신청", "birth": "1999-01-01",
                                         "address": "전북특별자치도 전주시 가상동 0", "employedAt": "2020-01-01"},
                             identity_json={"name": "가상신청", "birth": "1999-01-01"},
                             doc_context_json={"work_category": "직장가입자", "workplace_count": 1})
    with models.get_session() as session:
        session.add(app)
        session.commit()
        session.refresh(app)
    qualification, payment = documents(a, b, str(premium))
    qualification["fields"]["가구원수"] = str(size)
    if payment_problem == "missing-month":
        payment["fields"]["월별고지금액"] = json.dumps({"2025-10": str(premium), "2025-12": str(premium)})
    elif payment_problem == "untrusted":
        payment["status"] = "NEEDS_REVIEW"
    elif payment_problem == "invalid-amount":
        payment["fields"]["월별고지금액"] = json.dumps(dict.fromkeys(("2025-10", "2025-11", "2025-12"), "FAKE0"))
    elif payment_problem == "no-household":
        qualification["fields"].pop("가구원수")
    elif payment_problem == "explicit-conflict":
        qualification["fields"]["가입구분"] = "직장"
    fact_by_type = {str(DocType.NHIS_QUALIFICATION): qualification, str(DocType.NHIS_PAYMENT): payment}
    seen = set()
    requirements = checklist_for(app)
    if program_code == JOB_PACKAGE:
        requirements += [SimpleNamespace(doc_type=DocType.NHIS_QUALIFICATION, slot_key="FAKE_optional_qualification"),
                         SimpleNamespace(doc_type=DocType.NHIS_PAYMENT, slot_key="FAKE_optional_payment")]
    with models.get_session() as session:
        for req in requirements:
            if str(req.doc_type) in seen:
                continue
            seen.add(str(req.doc_type))
            fact = fact_by_type.get(str(req.doc_type), {})
            fields = {"성명": "가상신청", "생년월일": "1999-01-01", "발급일": "2026-04-07",
                      "전입일": "2020-01-01", **fact.get("fields", {})}
            row = models.Document(application_id=app.id, slot_key=req.slot_key,
                                  doc_type=str(req.doc_type), expected_doc_type=str(req.doc_type),
                                  file_path="FAKE-document.pdf", file_format="pdf", declared_issue_date=date(2026, 4, 7),
                                  stage1_status=fact.get("status", "PASS"),
                                  ocr_json={"confidence": .95, "image_quality": .95, "has_signature": True,
                                            "issue_date": "2026-04-07", "fields": fields, "bboxes": fact.get("bboxes", {})})
            session.add(row)
        session.commit()
    return app


def income_check(app, review):
    items = {item["key"]: item for item in review.score_json.get("items", [])}
    checks = _eligibility(Entry(app, review), items)
    return next((row for row in checks if row["key"] == "income"), None)


@pytest.mark.parametrize("a,b,expected", [
    ("확실한 공란", "확실한 공란", "FAIL"),
    ("값 있음", "값 있음", "PASS"),
    ("값 있음", "확실한 공란", "NEEDS_REVIEW"),
    ("확실한 공란", "값 있음", "NEEDS_REVIEW"),
    ("값 있음", "못 읽음", "NEEDS_REVIEW"),
    ("못 읽음", "값 있음", "NEEDS_REVIEW"),
    ("못 읽음", "못 읽음", "NEEDS_REVIEW"),
])
def test_middle_band_membership_controls_final_review_and_checklist(isolated_db, a, b, expected):
    app = make_application(a=a, b=b)
    review = _run_review(app)
    assert review.final_status == review.stage2_status == review.review_payload_json["final_status"] == expected
    check = income_check(app, review)
    item = next(item for item in review.score_json["items"] if item["key"] == "income")
    assert check["ok"] is (expected == "PASS")
    assert check["basis"] == item["basis"]
    reasons = {row["code"]: row for row in review.review_payload_json["reasons"]}
    assert ("INCOME_OVER_THRESHOLD" in reasons) is (expected == "FAIL")
    assert ("INCOME_UNDETERMINED" in reasons) is (expected == "NEEDS_REVIEW")
    if expected == "NEEDS_REVIEW":
        assert reasons["INCOME_UNDETERMINED"]["message"] == item["basis"]
        assert reasons["INCOME_UNDETERMINED"]["detail_codes"] == review.score_json["income_reason_codes"]
        assert review.review_payload_json["recommended_action"] == "담당자 재검토 필요"
    assert review.review_payload_json["documents"]
    assert all(row["file_ref"] for row in review.review_payload_json["documents"])


@pytest.mark.parametrize("a,b", [("값 있음", "확실한 공란"), ("못 읽음", "못 읽음")])
@pytest.mark.parametrize("band", ["low", "high"])
def test_category_independent_thresholds_propagate_even_when_evidence_disagrees(isolated_db, a, b, band):
    row = MEDIAN_INCOME_140[1]
    premium = row["지역"] if band == "low" else row["직장"] + 1
    review = _run_review(make_application(a=a, b=b, premium=premium))
    assert review.final_status == ("PASS" if band == "low" else "FAIL")
    assert review.score_json["income_status"] == ("MET" if band == "low" else "OVER_LIMIT")
    assert not any(reason["code"] == "INCOME_UNDETERMINED" for reason in review.review_payload_json["reasons"])


@pytest.mark.parametrize("category", ["직장", "지역"])
@pytest.mark.parametrize("offset", [0, 1])
def test_exact_limit_and_plus_one_use_authoritative_bool_despite_rounded_percent(isolated_db, category, offset):
    state = "값 있음" if category == "직장" else "확실한 공란"
    app = make_application(a=state, b=state, premium=MEDIAN_INCOME_140[1][category] + offset)
    review = _run_review(app)
    assert review.score_json["income_percent"] == 140.0
    assert review.final_status == ("PASS" if offset == 0 else "FAIL")
    assert review.score_json["income_over_limit"] is (offset == 1)
    assert income_check(app, review)["ok"] is (offset == 0)


@pytest.mark.parametrize("problem,detail", [("missing-month", "PREMIUM_MONTH_MISSING"),
                                           ("untrusted", "PREMIUM_UNTRUSTED"),
                                           ("invalid-amount", "PREMIUM_AMOUNT_INVALID"),
                                           ("no-household", "HOUSEHOLD_SIZE_UNCONFIRMED"),
                                           ("explicit-conflict", "INSURANCE_EXPLICIT_CONFLICT")])
def test_uncertain_income_never_leaks_into_pass_or_definite_rejection(isolated_db, problem, detail):
    app = make_application(payment_problem=problem)
    review = _run_review(app)
    assert review.final_status == review.stage2_status == review.review_payload_json["final_status"] == "NEEDS_REVIEW"
    reasons = {row["code"]: row for row in review.review_payload_json["reasons"]}
    assert detail in reasons["INCOME_UNDETERMINED"]["detail_codes"]
    assert "INCOME_OVER_THRESHOLD" not in reasons
    assert not income_check(app, review)["ok"]
    if problem == "no-household":
        assert "HEALTH_INSURANCE_HOUSEHOLD_SIZE_UNCONFIRMED" in reasons


@pytest.mark.parametrize("size", [8, 10, 11])
def test_large_households_use_official_rows_or_final_review(isolated_db, size):
    app = make_application(a="값 있음", b="값 있음", size=size, premium=0)
    review = _run_review(app)
    assert review.final_status == ("NEEDS_REVIEW" if size == 11 else "PASS")
    assert income_check(app, review)["ok"] is (size != 11)
    if size != 11:
        assert not any("표 밖" in note or "담당자 확인" in note for note in review.score_json["notes"])


@pytest.mark.parametrize("problem", [None, "missing-month", "untrusted", "explicit-conflict"])
def test_job_package_has_no_income_outcome_or_income_checklist(isolated_db, problem):
    app = make_application(program_code=JOB_PACKAGE, payment_problem=problem, premium=999999999, size=11)
    review = _run_review(app)
    assert review.final_status == "PASS"
    assert review.score_json == {}
    assert review.total_score is None
    assert not any(reason["code"].startswith("INCOME") for reason in review.review_payload_json["reasons"])
    assert income_check(app, review) is None
    assert review.supplement_deadline is None


@pytest.mark.parametrize("percent,over,expected", [(140.0, True, 10), (141.0, False, 9),
                                                   (None, True, 10), (None, False, None),
                                                   (140.0, None, 9), (141.0, None, 10)])
def test_adapter_uses_optional_integer_decision_without_breaking_legacy_percent_callers(percent, over, expected):
    applicant = to_engine_applicant(application_no="FAKE", name="가상신청", birth_date=date(1999, 1, 1),
                                    residence_region="전주시", program=PROGRAMS[DOUBLE_SAVINGS],
                                    income_percent=percent, income_over_limit=over)
    assert applicant.income_decile == expected


def test_supplement_deadline_and_action_follow_final_overridden_state(isolated_db):
    app = make_application(a="못 읽음", b="못 읽음")
    with models.get_session() as session:
        snapshot = criteria.for_application(app)
        snapshot.criteria_json = {**snapshot.criteria_json, "supplement": {"allowed": True, "days": 7}}
        session.add(snapshot)
        session.commit()
    review = _run_review(app)
    assert review.stage1_status == "PASS"
    assert review.final_status == "NEEDS_REVIEW"
    assert review.supplement_deadline is not None
    assert review.review_payload_json["recommended_action"] == "담당자 재검토 필요"
