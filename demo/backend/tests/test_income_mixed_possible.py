"""Public table boundaries and fictitious evidence never infer mixed membership."""
import pytest

from demo.backend.api.review import _run_review
from demo.backend.rules.facts import build_facts
from demo.backend.rules.scoring import MEDIAN_INCOME_140, score_income
from demo.backend.tests.test_income_facts import documents
from demo.backend.tests.test_income_review import isolated_db, income_check, make_application


@pytest.mark.parametrize("size", range(2, 11))
@pytest.mark.parametrize("a,b", [("값 있음", "값 있음"), ("확실한 공란", "확실한 공란"),
                                 ("못 읽음", "못 읽음"), ("값 있음", "확실한 공란")])
@pytest.mark.parametrize("position", ["above-ordinary", "mixed-equality", "above-mixed"])
def test_mixed_possible_interval_uses_all_public_bounds_without_selecting_membership(size, a, b, position):
    row = MEDIAN_INCOME_140[size]
    premium = {"above-ordinary": max(row["직장"], row["지역"]) + 1,
               "mixed-equality": row["혼합"], "above-mixed": row["혼합"] + 1}[position]
    docs = documents(a, b, str(premium))
    docs[0]["fields"]["가구원수"] = str(size)
    facts = build_facts({}, docs)
    category_before = facts.insurance_type
    result = score_income(facts)
    above = position == "above-mixed"
    assert result.status == ("OVER_LIMIT" if above else "UNDETERMINED")
    assert result.over_limit is above
    assert result.item.incomplete is not above
    assert (result.percent is None) is not above
    assert facts.insurance_type == category_before
    assert "혼합가입자" not in result.item.basis
    assert result.reason_codes == (["INCOME_ABOVE_ALL_LIMITS"] if above else ["INCOME_MIXED_POSSIBLE"])
    if not above:
        assert "혼합 가구 여부를 확정할 수 없습니다" in result.item.basis
        assert "담당자 재검토" in result.item.basis
        assert result.item.basis in result.notes


@pytest.mark.parametrize("size", [2, 10])
@pytest.mark.parametrize("position", ["above-ordinary", "mixed-equality", "above-mixed"])
def test_mixed_boundaries_reach_final_payload_and_officer_checklist(isolated_db, size, position):
    row = MEDIAN_INCOME_140[size]
    premium = {"above-ordinary": max(row["직장"], row["지역"]) + 1,
               "mixed-equality": row["혼합"], "above-mixed": row["혼합"] + 1}[position]
    app = make_application(size=size, premium=premium)
    review = _run_review(app)
    expected = "FAIL" if position == "above-mixed" else "NEEDS_REVIEW"
    payload = review.review_payload_json
    assert review.final_status == review.stage2_status == payload["final_status"] == expected
    assert payload["recommended_action"] == ("반려/보완요청 안내" if expected == "FAIL" else "담당자 재검토 필요")
    check = income_check(app, review)
    assert not check["ok"]
    item = next(item for item in review.score_json["items"] if item["key"] == "income")
    assert check["basis"] == item["basis"]
    if expected == "NEEDS_REVIEW":
        reason = next(row for row in payload["reasons"] if row["code"] == "INCOME_UNDETERMINED")
        assert reason["detail_codes"] == review.score_json["income_reason_codes"] == ["INCOME_MIXED_POSSIBLE"]
        assert reason["message"] == check["basis"]
        assert not any(row["code"] == "INCOME_OVER_THRESHOLD" for row in payload["reasons"])
    else:
        assert any(row["code"] == "INCOME_OVER_THRESHOLD" for row in payload["reasons"])


@pytest.mark.parametrize("position", ["regional-plus-one", "workplace-equality", "workplace-plus-one"])
def test_one_person_two_definite_blanks_preserve_regional_excess(isolated_db, position):
    row = MEDIAN_INCOME_140[1]
    premium = {"regional-plus-one": row["지역"] + 1, "workplace-equality": row["직장"],
               "workplace-plus-one": row["직장"] + 1}[position]
    docs = documents("확실한 공란", "확실한 공란", str(premium))
    facts = build_facts({}, docs)
    assert facts.insurance_type == "지역"
    income = score_income(facts)
    assert income.status == "OVER_LIMIT"
    assert income.over_limit
    app = make_application(premium=premium)
    review = _run_review(app)
    assert review.final_status == review.stage2_status == review.review_payload_json["final_status"] == "FAIL"
    assert review.score_json["income_status"] == "OVER_LIMIT"
    assert not income_check(app, review)["ok"]
