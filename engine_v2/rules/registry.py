"""규칙 유형 구현. 규칙팩(YAML)은 '어떤 값으로'를, 여기는 '어떻게 판단하는지'를 정한다.

규칙 함수 시그니처:  fn(ctx: RuleContext, params: dict) -> (CheckStatus, vars: dict)
  - 판단에 필요한 필드가 없으면 UNKNOWN (→ 검토필요)
  - vars는 메시지 템플릿 {중괄호}에 채워진다
새 규칙 유형은 @rule("이름")만 붙이면 등록된다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable

from schemas.models import ApplicantInput, CheckStatus, DocType, ExtractedField

PASS, FAIL, UNKNOWN = CheckStatus.PASS, CheckStatus.FAIL, CheckStatus.UNKNOWN


@dataclass
class RuleContext:
    reference_date: date
    applicant: ApplicantInput
    declared_values: dict[str, Any]
    detected_type: DocType
    fields: dict[str, ExtractedField]
    validations: dict[str, tuple[bool, str]] = field(default_factory=dict)  # 이름 → (통과, 설명)


RuleFn = Callable[[RuleContext, dict], tuple[CheckStatus, dict]]
RULES: dict[str, RuleFn] = {}


def rule(name: str):
    def deco(fn: RuleFn) -> RuleFn:
        RULES[name] = fn
        return fn
    return deco


def _val(ctx: RuleContext, key: str):
    f = ctx.fields.get(key)
    return None if f is None else f.value


def _as_date(v) -> date | None:
    if v is None or isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v))
    except ValueError:
        return None


def _age(birth: date, on: date) -> int:
    return on.year - birth.year - ((on.month, on.day) < (birth.month, birth.day))


def _months(a: date, b: date) -> int:
    m = (b.year - a.year) * 12 + (b.month - a.month)
    return m - 1 if b.day < a.day else m


# --- 공통 ---------------------------------------------------------------
@rule("doc_type_is")
def doc_type_is(ctx, p):
    ok = ctx.detected_type.value == p["expected"]
    return (PASS if ok else FAIL), {"detected_type": ctx.detected_type.value}


@rule("validation_passed")
def validation_passed(ctx, p):
    v = ctx.validations.get(p["validation"])
    if v is None:
        return UNKNOWN, {"detail": "검증 결과 없음"}
    return (PASS if v[0] else FAIL), {"detail": v[1]}


@rule("equals_declared")
def equals_declared(ctx, p):
    value, declared = _val(ctx, p["field"]), ctx.declared_values.get(p["declared"])
    if value is None or declared is None:
        return UNKNOWN, {"value": value, "declared": declared}
    if isinstance(value, date):
        declared = _as_date(declared)
    return (PASS if value == declared else FAIL), {"value": value, "declared": declared}


@rule("equals_applicant")
def equals_applicant(ctx, p):
    value, declared = _val(ctx, p["field"]), getattr(ctx.applicant, p["applicant"], None)
    if value is None or declared is None:
        return UNKNOWN, {"value": value, "declared": declared}
    if isinstance(value, str):
        value, declared = value.replace(" ", ""), str(declared).replace(" ", "")
    return (PASS if value == declared else FAIL), {"value": value, "declared": declared}


@rule("date_within_days")
def date_within_days(ctx, p):
    d = _as_date(_val(ctx, p["field"]))
    if d is None:
        return UNKNOWN, {}
    days = (ctx.reference_date - d).days
    ok = 0 <= days <= p["max_days"] if p.get("not_after_reference", False) else days <= p["max_days"]
    return (PASS if ok else FAIL), {"value": d, "days": days, "max_days": p["max_days"],
                                     "reference_date": ctx.reference_date}


@rule("date_in_range")
def date_in_range(ctx, p):
    d = _as_date(_val(ctx, p["field"]))
    if d is None:
        return UNKNOWN, {}
    start, end = _as_date(p["start"]), _as_date(p["end"])
    return (PASS if start <= d <= end else FAIL), {"value": d, "start": start, "end": end}


@rule("date_order")
def date_order(ctx, p):
    a, b = _as_date(_val(ctx, p["before"])), _as_date(_val(ctx, p["after"]))
    if a is None or b is None:
        return UNKNOWN, {"before": a, "after": b}
    gap = (b - a).days
    ok = 0 <= gap <= p.get("max_gap_days", 10**6)
    return (PASS if ok else FAIL), {"before": a, "after": b, "gap": gap}


@rule("amount_equals")
def amount_equals(ctx, p):
    a, b = _val(ctx, p["field"]), _val(ctx, p["other"]) if "other" in p else ctx.declared_values.get(p["declared"])
    if a is None or b is None:
        return UNKNOWN, {"value": a, "other": b}
    return (PASS if int(a) == int(b) else FAIL), {"value": a, "other": b}


# --- 초본 ---------------------------------------------------------------
@rule("age_between")
def age_between(ctx, p):
    b = _as_date(_val(ctx, p["field"]))
    if b is None:
        return UNKNOWN, {}
    age = _age(b, ctx.reference_date)
    return (PASS if p["min"] <= age <= p["max"] else FAIL), {"age": age, "min": p["min"], "max": p["max"]}


@rule("current_sido_is")
def current_sido_is(ctx, p):
    hist = _val(ctx, "address_history") or []
    sido = hist[-1]["sido"] if hist else None
    if sido is None:
        return UNKNOWN, {"sido": None}
    return (PASS if sido == p["sido"] else FAIL), {"sido": sido}


@rule("residence_months_at_least")
def residence_months_at_least(ctx, p):
    hist = _val(ctx, "address_history") or []
    if not hist:
        return UNKNOWN, {}
    start = None
    for h in reversed(hist):           # 맨 뒤부터 같은 시도가 이어지는 동안 거슬러 올라감
        if h["sido"] != p["sido"]:
            break
        start = _as_date(h.get("occurred")) or _as_date(h.get("reported")) or start
    if start is None:
        return FAIL, {"start": None, "months": 0, "min_months": p["months"]}
    months = _months(start, ctx.reference_date)
    return (PASS if months >= p["months"] else FAIL), {"start": start, "months": months, "min_months": p["months"]}
