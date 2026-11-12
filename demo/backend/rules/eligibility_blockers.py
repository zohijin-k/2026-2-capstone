"""Applicant-safe eligibility reasons; never expose score items or internal ranks."""
from datetime import date
from typing import Any
from .age_eligibility import assess_age
from .facts import build_facts
from .months import format_month_ranges
from .programs import ProgramConfig
from .scoring import MEDIAN_INCOME_140, score_income


def _recovery(program: ProgramConfig) -> str:
    return ("서류를 잘못 올렸다면 서류 업로드에서 다시 올려 주세요. "
            f"문의: 콜센터 {program.call_center}.")


def age_blockers(program: ProgramConfig, form1: dict[str, Any], identity: dict[str, Any] | None):
    age = assess_age(program, form1.get("birth"), identity)
    if age.reason_code != "AGE_OUT_OF_RANGE":
        return []
    return [{"kind": "eligibility", "target": "age", "label": "연령 요건",
             "code": age.reason_code, "message": age.basis + ". " + _recovery(program), "goto": "form1",
             "evidence": {"birth_date": age.birth_date.isoformat(),
                          "birth_range": [value.isoformat() for value in program.birth_range]}}]


def eligibility_blockers(program: ProgramConfig, form1: dict[str, Any], identity: dict[str, Any] | None,
                         documents: list[dict[str, Any]], work_category: str | None,
                         criteria: dict[str, Any]) -> list[dict[str, Any]]:
    items = age_blockers(program, form1, identity)
    if program.has_income_requirement:
        months = criteria.get("nhis_payment_months")
        facts = build_facts(form1, documents, months)
        income = score_income(facts)
        if income.status == "OVER_LIMIT":
            row = MEDIAN_INCOME_140[facts.household_size]
            category = facts.insurance_type if facts.insurance_type in {"직장", "지역"} else None
            limits = {category: row[category]} if category else row
            rendered_limits = " · ".join(f"{key} {value:,}원" for key, value in limits.items())
            period = format_month_ranges(months) if months else "심사 대상 석 달"
            message = (f"건강보험 자격확인서 가구원 {facts.household_size}명, 적용 기준 {rendered_limits} "
                       f"(중위소득 140%). 본인 {period} 평균 고지금액 {facts.monthly_premium:,}원이 기준을 초과합니다. "
                       + _recovery(program))
            items.append({"kind": "eligibility", "target": "income", "label": "소득 요건",
                          "code": "OVER_LIMIT", "message": message, "goto": "upload",
                          "evidence": {"household_size": facts.household_size,
                                       "insurance_type": category or "직장·지역 구분 미확정",
                                       "limits_140": limits, "months": months,
                                       "monthly_premium": facts.monthly_premium}})
    if program.has_work_requirement:
        from .work_continuity import assess_work
        work = assess_work(program, date.fromisoformat(criteria["announcement_date"]),
                           work_category, documents, identity)
        if work.status == "NOT_MET":
            items.append({"kind": "eligibility", "target": "work", "label": "근로 계속성 요건",
                          "code": "WORK_CONTINUITY_NOT_MET", "detail_codes": work.detail_codes,
                          "message": work.basis + " " + _recovery(program), "goto": "upload",
                          "evidence": work.as_dict()})
    return items
