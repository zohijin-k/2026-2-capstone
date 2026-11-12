"""Income eligibility uses exact integer limits independently of score estimates."""
from datetime import date

import pytest

from demo.backend.rules.facts import build_facts
from demo.backend.rules.scoring import (
    ESTIMATE_LABEL, MEDIAN_INCOME_140, ScoringFacts,
    income_percent, premium_limit_140, score_application, score_income,
)
from demo.backend.tests.test_income_facts import documents


@pytest.mark.parametrize("size", range(1, 11))
@pytest.mark.parametrize("category", ["직장", "지역"])
@pytest.mark.parametrize("offset", [0, 1])
def test_each_official_threshold_is_inclusive_with_exact_plus_one_outcome(size, category, offset):
    limit = MEDIAN_INCOME_140[size][category]
    result = score_income(ScoringFacts(household_size=size, monthly_premium=limit + offset, insurance_type=category))
    mixed_possible = size >= 2 and category == "직장" and offset == 1
    assert result.status == ("UNDETERMINED" if mixed_possible else "MET" if offset == 0 else "OVER_LIMIT")
    assert result.over_limit is (offset == 1 and not mixed_possible)
    assert result.percent == (None if mixed_possible else 140.0)
    assert result.item.incomplete is mixed_possible
    if mixed_possible:
        assert result.reason_codes == ["INCOME_MIXED_POSSIBLE"]
    assert "담당자 확인" not in result.item.basis
    assert result.reason_codes


@pytest.mark.parametrize("a", ["값 있음", "확실한 공란", "못 읽음"])
@pytest.mark.parametrize("b", ["값 있음", "확실한 공란", "못 읽음"])
@pytest.mark.parametrize("amount_band", ["low", "middle", "high"])
def test_ab_matrix_follows_both_limits_before_membership_requirement(a, b, amount_band):
    row = MEDIAN_INCOME_140[1]
    premium = {"low": min(row.values()), "middle": min(row.values()) + 1, "high": max(row.values()) + 1}[amount_band]
    facts = build_facts({}, documents(a, b, str(premium)))
    result = score_income(facts)
    expected = ("MET" if amount_band == "low" else "OVER_LIMIT" if amount_band == "high" else
                "MET" if a == b == "값 있음" else "OVER_LIMIT" if a == b == "확실한 공란" else "UNDETERMINED")
    assert result.status == expected
    assert result.over_limit is (expected == "OVER_LIMIT")
    assert result.item.incomplete is (expected == "UNDETERMINED")
    assert (result.percent is None) is (expected == "UNDETERMINED")
    assert facts.insurance_type == ("직장" if a == b == "값 있음" else "지역" if a == b == "확실한 공란" else "모름")


@pytest.mark.parametrize("premium", [0, MEDIAN_INCOME_140[1]["지역"], MEDIAN_INCOME_140[1]["직장"] + 1])
def test_conflicting_recorded_category_requires_review_even_outside_membership_sensitive_band(premium):
    docs = documents("확실한 공란", "확실한 공란", str(premium))
    docs[0]["fields"]["가입구분"] = "직장"
    result = score_income(build_facts({}, docs))
    assert result.status == "UNDETERMINED"
    assert not result.over_limit
    assert result.percent is None
    assert "INSURANCE_EXPLICIT_CONFLICT" in result.reason_codes


@pytest.mark.parametrize("category", ["모름", "혼합", "unknown"])
def test_unknown_and_mixed_membership_never_select_the_mixed_limit_in_middle_band(category):
    result = score_income(ScoringFacts(household_size=1, monthly_premium=MEDIAN_INCOME_140[1]["지역"] + 1,
                                      insurance_type=category))
    assert result.status == "UNDETERMINED"
    assert result.item.incomplete
    assert result.percent is None


@pytest.mark.parametrize("premium", [0, MEDIAN_INCOME_140[2]["지역"], MEDIAN_INCOME_140[2]["직장"] + 1])
def test_unconfirmed_category_has_disclosed_demo_score_reference_without_becoming_membership_fact(premium):
    facts = ScoringFacts(household_size=2, monthly_premium=premium)
    result = score_income(facts)
    mixed_possible = premium > MEDIAN_INCOME_140[2]["직장"]
    assert result.status == ("UNDETERMINED" if mixed_possible else "MET")
    assert facts.insurance_type == "모름"
    assert "모름가입자" not in result.item.basis
    if mixed_possible:
        assert result.percent is None
        assert not result.over_limit
        assert result.item.incomplete
        assert result.reason_codes == ["INCOME_MIXED_POSSIBLE"]
        assert "혼합 가구 여부를 확정할 수 없습니다" in result.item.basis
    else:
        assert "가입구분 미확정" in result.item.basis
        assert any("가입구분 미확정" in note and ESTIMATE_LABEL in note for note in result.notes)


@pytest.mark.parametrize("size", [None, 0, -1, 11, 99, True, "1"])
def test_unsupported_household_never_clamps_or_yields_a_definite_outcome(size):
    result = score_income(ScoringFacts(household_size=size, monthly_premium=999999999, insurance_type="직장"))
    assert result.status == "UNDETERMINED"
    assert not result.over_limit
    assert result.percent is None
    assert result.item.incomplete
    assert any(code.startswith("HOUSEHOLD_SIZE_") for code in result.reason_codes)


@pytest.mark.parametrize("premium", [None, -1, 1.5, True, "50000"])
def test_missing_or_invalid_pure_premium_requires_review(premium):
    result = score_income(ScoringFacts(household_size=1, monthly_premium=premium, insurance_type="지역"))
    assert result.status == "UNDETERMINED"
    assert not result.over_limit


@pytest.mark.parametrize("reason", ["PREMIUM_MONTH_MISSING", "PREMIUM_UNTRUSTED", "PREMIUM_AMOUNT_INVALID"])
def test_explicit_untrusted_flag_cannot_be_overridden_by_a_numeric_value(reason):
    result = score_income(ScoringFacts(household_size=1, monthly_premium=999999999, insurance_type="직장",
                                      premium_determinable=False, premium_reason_code=reason,
                                      premium_issue="가상 판독 불확실"))
    assert result.status == "UNDETERMINED"
    assert reason in result.reason_codes
    assert "가상 판독 불확실" in result.item.basis


@pytest.mark.parametrize("size", [8, 10])
def test_large_official_households_have_no_out_of_notice_or_manual_review_warning(size):
    result = score_income(ScoringFacts(household_size=size, monthly_premium=MEDIAN_INCOME_140[size]["직장"],
                                      insurance_type="직장"))
    assert result.status == "MET"
    assert premium_limit_140(size, "직장")[1] == ""
    assert not any("표 밖" in note or "담당자 확인" in note or "7인" in note for note in result.notes)


@pytest.mark.parametrize("size", [0, -1, 11, 100, True])
def test_direct_premium_table_lookup_does_not_clamp(size):
    with pytest.raises(ValueError):
        premium_limit_140(size, "직장")


def test_table_helpers_preserve_informational_mixed_values_without_automatic_selection():
    assert premium_limit_140(1, "혼합")[0] == MEDIAN_INCOME_140[1]["직장"]
    assert ESTIMATE_LABEL in premium_limit_140(1, "혼합")[1]
    for size in range(2, 11):
        assert premium_limit_140(size, "혼합") == (MEDIAN_INCOME_140[size]["혼합"], "")
        result = score_income(ScoringFacts(household_size=size, monthly_premium=MEDIAN_INCOME_140[size]["혼합"],
                                          insurance_type="혼합"))
        assert result.status == "UNDETERMINED"
        assert result.reason_codes == ["INCOME_MIXED_POSSIBLE"]
        assert not result.over_limit
        assert result.percent is None
        assert result.item.incomplete
        assert "혼합가입자" not in result.item.basis


def test_named_result_retains_four_value_unpacking_indexing_and_serializes_authoritative_state():
    facts = build_facts({}, documents("확실한 공란", "확실한 공란", str(MEDIAN_INCOME_140[1]["지역"] + 1)))
    result = score_income(facts)
    item, percent, over, notes = result
    assert (item, percent, over, notes) == tuple(result)
    assert result[0] is item
    assert result[-1] is notes
    assert result[:2] == (item, percent)
    assert len(result) == 4
    assert "사업장관리번호 확실한 공란(지역)" in item.basis
    assert "사업장명칭 확실한 공란(지역)" in item.basis
    sheet = score_application(facts, announcement_date=date(2026, 3, 3), age_basis_date=date(2025, 12, 31))
    assert sheet.income_status == sheet.as_dict()["income_status"] == "OVER_LIMIT"
    assert sheet.income_reason_codes == sheet.as_dict()["income_reason_codes"] == result.reason_codes
    assert sheet.income_over_limit


def test_existing_linear_score_estimate_and_household_reference_note_remain():
    facts = ScoringFacts(household_size=4, monthly_premium=200000, insurance_type="직장",
                         household_size_form_mismatch=(3, 4))
    result = score_income(facts)
    percent, baseline, _ = income_percent(4, 200000, "직장")
    assert (round(percent, 1), baseline) == (90.0, 222165)
    assert result.item.score == 40
    assert result.percent == 90.0
    assert any("신청서 입력 가구원수 3명" in note for note in result.notes)
    assert any(ESTIMATE_LABEL in note and "선형 환산" in note for note in result.notes)
