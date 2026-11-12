"""Uncertain payment amounts cannot trigger an income eligibility rejection."""
from datetime import date

import pytest

from demo.backend.engine_adapter import run_pipeline, to_engine_applicant, to_engine_documents
from demo.backend.ocr.localocr import _from_nhis
from demo.backend.rules.doc_check import check_document
from demo.backend.rules.doc_types import DocType
from demo.backend.rules.facts import PAYMENT_AMOUNT_FIELDS, _field, build_facts
from demo.backend.rules.identity import Identity
from demo.backend.rules.programs import DOUBLE_SAVINGS, PROGRAMS
from demo.backend.rules.required_docs import DocRequirement
from demo.backend.rules.scoring import score_application
from engine_v2.extractors import nhis_payment
from engine_v2.schemas.models import DocType as V2DocType
from engine_v2.tests import p2_payment_samples as sample


def payment_fact(*, damaged=False, wrong_identity=False, high=False):
    cells, size = sample.payment()
    if high:
        cells = [(*cell[:4], "9,100,000", cell[5]) if cell[4] == "100,000" else cell for cell in cells]
    if high and not damaged:
        cells = [(*cell[:4], "9,150,000", cell[5]) if cell[4] == "150,000" else cell for cell in cells]
        cells = [(*cell[:4], "9,165,000", cell[5]) if cell[0] == 738 else cell for cell in cells]
    pages = [sample.page(cells, size=size)]
    ocr = _from_nhis(nhis_payment.extract(pages), pages, V2DocType)
    requirement = DocRequirement("nhis_payment", DocType.NHIS_PAYMENT, "가상 납부확인서",
                                 min_issue_date=date(2026, 3, 3))
    identity_name = "가상다름" if wrong_identity else sample.NAME
    verdict = check_document(requirement, ocr, identity=Identity(identity_name, date(1990, 1, 1)))
    return {"doc_type": str(DocType.NHIS_PAYMENT), "fields": ocr.fields, "status": verdict.status,
            "confidence": ocr.confidence, "image_quality": ocr.image_quality,
            "issue_date": ocr.issue_date, "file_format": "pdf"}, requirement


@pytest.mark.parametrize("problem", ["arithmetic", "identity"])
@pytest.mark.parametrize("structure_marker", [False, True])
def test_partial_or_other_person_payment_cannot_establish_excess_income(problem, structure_marker):
    payment, requirement = payment_fact(damaged=problem == "arithmetic", wrong_identity=problem == "identity", high=True)
    if not structure_marker:
        payment["fields"].pop("양식판독상태")
    assert payment["status"] == "NEEDS_REVIEW"
    assert int(payment["fields"]["건강보험료"]) > 1_000_000
    qualification = {"doc_type": str(DocType.NHIS_QUALIFICATION), "fields": {"가구원수": "1"}}
    facts = build_facts({"birth": sample.BIRTH}, [payment, qualification], ["2025-10", "2025-11", "2025-12"])
    assert facts.monthly_premium is None
    assert all(_field(payment, key) is None for key in PAYMENT_AMOUNT_FIELDS)
    assert "채점 보류" in facts.source("income").origin
    program = PROGRAMS[DOUBLE_SAVINGS]
    sheet = score_application(facts, announcement_date=program.announcement_date, age_basis_date=program.age_basis_date)
    assert sheet.income_percent is None
    applicant = to_engine_applicant(application_no="FAKE", name=sample.NAME, birth_date=date(1990, 1, 1),
                                    residence_region="전주시", program=program, income_percent=sheet.income_percent)
    result = run_pipeline(applicant, to_engine_documents([payment]), [requirement])
    assert all(finding.code.value != "INCOME_OVER_THRESHOLD" for finding in result.stage2.findings)
    assert result.stage1.status.value == "NEEDS_REVIEW"
    assert result.status.value == "NEEDS_REVIEW"


@pytest.mark.parametrize("high", [False, True])
def test_complete_matching_payment_preserves_income_scoring(high):
    payment, _ = payment_fact(high=high)
    assert payment["status"] == "PASS"
    facts = build_facts({}, [payment, {"doc_type": str(DocType.NHIS_QUALIFICATION), "fields": {"가구원수": "1"}}])
    assert facts.monthly_premium == int(payment["fields"]["건강보험료"])
    program = PROGRAMS[DOUBLE_SAVINGS]
    sheet = score_application(facts, announcement_date=program.announcement_date, age_basis_date=program.age_basis_date)
    assert sheet.income_status == ("OVER_LIMIT" if high else "UNDETERMINED")
    assert sheet.income_over_limit is high
    if high:
        assert sheet.income_percent is not None
        assert sheet.income_percent > 140
    else:
        # B is an observed regional blank, but A is missing in this sample.
        # This middle-band amount cannot inherit the old workplace default.
        assert sheet.income_percent is None
        assert sheet.items[0].incomplete
        assert "INSURANCE_EVIDENCE_INSUFFICIENT" in sheet.income_reason_codes


@pytest.mark.parametrize("status", ["NEEDS_REVIEW", "FAIL"])
def test_marked_payment_status_suppresses_financial_fields(status):
    payment, _ = payment_fact()
    payment["status"] = status
    assert _field(payment, "건강보험료") is None
    assert _field(payment, "성명") == sample.NAME


def test_statusless_complete_or_legacy_payment_keeps_existing_fact_contract():
    payment, _ = payment_fact()
    payment.pop("status")
    assert _field(payment, "건강보험료") == "50000"
    payment["fields"].pop("양식판독상태")
    assert _field(payment, "건강보험료") == "50000"


@pytest.mark.parametrize("status", ["NEEDS_REVIEW", "FAIL"])
def test_markerless_payment_status_suppresses_financial_fields(status):
    payment, _ = payment_fact()
    payment["fields"].pop("양식판독상태")
    payment["status"] = status
    assert all(_field(payment, key) is None for key in PAYMENT_AMOUNT_FIELDS)
    assert _field(payment, "성명") == sample.NAME


@pytest.mark.parametrize("status,expected", [(None, .95), ("PASS", .95), ("NEEDS_REVIEW", .4), ("FAIL", .95)])
def test_engine_adapter_carries_explicit_review_without_mutating_saved_confidence(status, expected):
    payment, _ = payment_fact()
    if status is None:
        payment.pop("status")
    else:
        payment["status"] = status
    converted = to_engine_documents([payment])[0]
    assert converted.ocr_confidence == expected
    assert payment["confidence"] == .95
    assert converted.extracted_fields == payment["fields"]


@pytest.mark.parametrize("include_status", [False, True])
def test_complete_matching_payment_keeps_pipeline_pass(include_status):
    payment, requirement = payment_fact()
    if not include_status:
        payment.pop("status")
    applicant = to_engine_applicant(application_no="FAKE", name=sample.NAME, birth_date=date(1990, 1, 1),
                                    residence_region="전주시", program=PROGRAMS[DOUBLE_SAVINGS], income_percent=90)
    result = run_pipeline(applicant, to_engine_documents([payment]), [requirement])
    assert result.status.value == "PASS"


def test_already_uncertain_review_confidence_is_preserved():
    payment, _ = payment_fact()
    payment["status"] = "NEEDS_REVIEW"
    payment["confidence"] = .8
    assert to_engine_documents([payment])[0].ocr_confidence == .8
