"""Fictitious income evidence and complete billed-month fact contracts."""
import json
from copy import deepcopy

import pytest

from demo.backend.ocr.fixture import FIXTURES
from demo.backend.rules.doc_types import DocType
from demo.backend.rules.facts import DEFAULT_PAYMENT_MONTHS, build_facts
from demo.backend.rules.scoring import ScoringFacts


def documents(a="확실한 공란", b="확실한 공란", premium="50000"):
    qualification = {"doc_type": str(DocType.NHIS_QUALIFICATION), "document_id": 101,
                     "status": "PASS", "confidence": .95,
                     "fields": {"가구원수": "1", "양식판독상태": "완전"},
                     "bboxes": {"사업장관리번호_상태": {"page": 0, "x0": 1, "y0": 2, "x1": 3, "y1": 4}}}
    payment = {"doc_type": str(DocType.NHIS_PAYMENT), "document_id": 202,
               "status": "PASS", "confidence": .95,
               "fields": {"건강보험료": "999999999", "양식판독상태": "완전",
                          "월별고지금액": json.dumps(dict.fromkeys(DEFAULT_PAYMENT_MONTHS, premium))},
               "bboxes": {"사업장명칭_상태": {"page": 0, "x0": 5, "y0": 6, "x1": 7, "y1": 8}}}
    for doc, label, state, present in ((qualification, "사업장관리번호", a, "00000000000"),
                                        (payment, "사업장명칭", b, "가상사업장")):
        if state is not None:
            doc["fields"][label + "_상태"] = state
            if state != "못 읽음":
                doc["fields"][label] = present if state == "값 있음" else ""
    return [qualification, payment]


@pytest.mark.parametrize("a", ["값 있음", "확실한 공란", "못 읽음", None])
@pytest.mark.parametrize("b", ["값 있음", "확실한 공란", "못 읽음", None])
def test_two_independent_states_determine_category_without_workplace_default(a, b):
    facts = build_facts({}, documents(a, b))
    expected = "직장" if a == b == "값 있음" else "지역" if a == b == "확실한 공란" else "모름"
    assert facts.insurance_type == expected
    assert facts.insurance_evidence["A"]["state"] == (a or "못 읽음")
    assert facts.insurance_evidence["B"]["state"] == (b or "못 읽음")
    assert not facts.insurance_explicit_conflict
    assert facts.monthly_premium == 50000
    assert facts.premium_determinable is True
    assert facts.source("insurance_a").document_id == 101
    assert facts.source("insurance_b").document_id == 202
    assert facts.source("insurance_a").bbox["x0"] == 1
    assert facts.insurance_evidence["B"]["source"] == facts.source("insurance_b").as_dict()
    assert "사업장관리번호" in facts.source("income").origin
    assert "사업장명칭" in facts.source("income").origin


@pytest.mark.parametrize("where", [0, 1])
@pytest.mark.parametrize("explicit", ["직장", "지역", "직장가입자", "지역가입자"])
def test_legacy_recorded_category_can_supply_missing_evidence(where, explicit):
    docs = documents(None, None)
    docs[where]["fields"]["가입구분"] = explicit
    docs[where].pop("confidence")
    docs[where].pop("status")
    docs[where]["fields"].pop("양식판독상태")
    facts = build_facts({}, docs)
    assert facts.insurance_type == explicit[:2]
    assert not facts.insurance_conflict
    source = facts.source("insurance_explicit_" + ("qualification" if where == 0 else "payment"))
    assert source.document_id == (101 if where == 0 else 202)


@pytest.mark.parametrize("a,b,q_explicit,p_explicit", [
    ("확실한 공란", "확실한 공란", "직장", None),
    (None, None, "직장", "지역"),
    ("값 있음", "확실한 공란", "직장", None),
    ("값 있음", "값 있음", None, "지역"),
])
def test_any_usable_recorded_category_conflict_is_distinct_from_cell_disagreement(a, b, q_explicit, p_explicit):
    docs = documents(a, b)
    for doc, value in zip(docs, (q_explicit, p_explicit)):
        if value:
            doc["fields"]["가입구분"] = value
    facts = build_facts({}, docs)
    assert facts.insurance_type == "모름"
    assert facts.insurance_conflict
    assert facts.insurance_explicit_conflict
    assert "INSURANCE_EXPLICIT_CONFLICT" in facts.insurance_reason_codes


def test_cell_disagreement_alone_has_no_explicit_conflict_override():
    facts = build_facts({}, documents("값 있음", "확실한 공란"))
    assert facts.insurance_conflict
    assert not facts.insurance_explicit_conflict
    assert facts.insurance_reason_codes == ["INSURANCE_EVIDENCE_CONFLICT"]


@pytest.mark.parametrize("defect", ["absent-value", "nonempty-blank", "malformed-number", "empty-present",
                                    "incomplete", "review", "low-confidence", "missing-confidence"])
def test_untrustworthy_or_state_inconsistent_a_cannot_establish_category(defect):
    docs = documents()
    fields = docs[0]["fields"]
    if defect == "absent-value":
        fields.pop("사업장관리번호")
    elif defect == "nonempty-blank":
        fields["사업장관리번호"] = "00000000000"
    elif defect == "malformed-number":
        fields["사업장관리번호_상태"], fields["사업장관리번호"] = "값 있음", "000X000"
    elif defect == "empty-present":
        fields["사업장관리번호_상태"] = "값 있음"
    elif defect == "incomplete":
        fields["양식판독상태"] = "불완전"
    elif defect == "review":
        docs[0]["status"] = "NEEDS_REVIEW"
    elif defect == "low-confidence":
        docs[0]["confidence"] = .84
    else:
        docs[0].pop("confidence")
    facts = build_facts({}, docs)
    assert facts.insurance_type == "모름"
    assert facts.insurance_evidence["A"]["state"] == "못 읽음"


@pytest.mark.parametrize("raw", ["", None, "사업장명칭", "???", "000000"])
def test_b_present_requires_a_complete_name_cell(raw):
    docs = documents("값 있음", "값 있음")
    docs[1]["fields"]["사업장명칭"] = raw
    facts = build_facts({}, docs)
    assert facts.insurance_evidence["B"]["state"] == "못 읽음"
    assert facts.insurance_type == "모름"


def test_mixed_recorded_category_is_not_automatically_selected():
    docs = documents(None, None)
    docs[0]["fields"]["가입구분"] = "혼합"
    facts = build_facts({}, docs)
    assert facts.insurance_type == "모름"
    assert "INSURANCE_TYPE_UNSUPPORTED" in facts.insurance_reason_codes


@pytest.mark.parametrize("raw", ["50000", "50,000", 50000, "0", 0])
def test_all_three_whole_integer_billed_amounts_are_used_including_zero(raw):
    facts = build_facts({}, documents(premium=raw))
    assert facts.monthly_premium == int(str(raw).replace(",", ""))
    assert facts.premium_determinable
    assert facts.premium_issue is None


@pytest.mark.parametrize("raw", [None, True, False, 1.5, -1, "-1", "50,00", "50000원", "5O000", "", "1.5"])
def test_malformed_month_is_not_repaired_by_stripping_characters(raw):
    facts = build_facts({}, documents(premium=raw))
    assert facts.monthly_premium is None
    assert facts.premium_determinable is False
    assert facts.premium_reason_code == "PREMIUM_AMOUNT_INVALID"


@pytest.mark.parametrize("missing", ["2025-10", "2025-11", "2025-12", "all", "bad-json", "list-json"])
def test_missing_monthly_data_never_falls_back_to_aggregate(missing):
    docs = documents()
    fields = docs[1]["fields"]
    monthly = json.loads(fields["월별고지금액"])
    if missing == "all":
        fields.pop("월별고지금액")
    elif missing == "bad-json":
        fields["월별고지금액"] = "not json"
    elif missing == "list-json":
        fields["월별고지금액"] = "[]"
    else:
        monthly.pop(missing)
        fields["월별고지금액"] = json.dumps(monthly)
    facts = build_facts({}, docs)
    assert facts.monthly_premium is None
    assert facts.premium_reason_code == "PREMIUM_MONTH_MISSING"


@pytest.mark.parametrize("confidence", [.84, None, "unknown", float("inf"), float("nan"), True])
def test_invalid_confidence_suppresses_payment_amounts(confidence):
    docs = documents()
    docs[1]["confidence"] = confidence
    facts = build_facts({}, docs)
    assert facts.monthly_premium is None
    assert facts.premium_reason_code == "PREMIUM_UNTRUSTED"


@pytest.mark.parametrize("status", ["FAIL", "NEEDS_REVIEW", "UNKNOWN"])
def test_supplied_nonnormal_status_suppresses_payment_amounts(status):
    docs = documents()
    docs[1]["status"] = status
    assert build_facts({}, docs).premium_reason_code == "PREMIUM_UNTRUSTED"


def test_selected_months_and_rounding_preserve_established_formula():
    docs = documents()
    values = {"2025-10": "0", "2025-11": "1", "2025-12": "1", "2026-01": "100"}
    docs[1]["fields"]["월별고지금액"] = json.dumps(values)
    assert build_facts({}, docs).monthly_premium == 1
    assert build_facts({}, docs, ["2025-11", "2025-12", "2026-01"]).monthly_premium == 34
    assert build_facts({}, docs, []).premium_reason_code == "PREMIUM_MONTHS_INVALID"


def test_fixture_payment_scenarios_keep_existing_established_premiums():
    for key in ("S2_건강보험료납부확인서_적합", "P9_건강보험료납부확인서_부모명의", "S7_건강보험료납부확인서_소득초과"):
        fixture = FIXTURES[key]
        payment = {"doc_type": str(DocType.NHIS_PAYMENT), "fields": deepcopy(fixture.fields), "confidence": fixture.confidence}
        facts = build_facts({}, [payment])
        assert facts.monthly_premium == int(fixture.fields["건강보험료"])
        assert facts.insurance_type == fixture.fields["가입구분"]
    assert ScoringFacts().insurance_type == "모름"
    assert ScoringFacts().premium_determinable is None


@pytest.mark.parametrize("metadata,value", [("status", "NEEDS_REVIEW"), ("confidence", .4),
                                            ("confidence", float("inf")), ("양식판독상태", "불완전"),
                                            ("판독검증실패", "household_rows_read")])
def test_cached_untrusted_qualification_count_cannot_establish_income(metadata, value):
    docs = documents()
    if metadata in {"status", "confidence"}:
        docs[0][metadata] = value
    else:
        docs[0]["fields"][metadata] = value
    facts = build_facts({}, docs)
    assert facts.household_size is None
    assert facts.household_size_issue
    assert docs[0]["fields"]["가구원수"] == "1"


def test_minimal_legacy_household_count_keeps_missing_metadata_compatibility():
    docs = documents(None, None)
    docs[0] = {"doc_type": str(DocType.NHIS_QUALIFICATION), "fields": {"가구원수": "1"}}
    facts = build_facts({}, docs)
    assert facts.household_size == 1
    assert facts.household_size_issue is None
