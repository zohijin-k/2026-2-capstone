"""신청자용 기준 조회 및 시·도 담당자 기준 버전 편집 API."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field as PydanticField
from sqlmodel import select

from ..models import ProgramCriteriaVersion, get_session
from ..rules.criteria import (
    CRITERIA_SCHEMA_VERSION,
    default_criteria,
    history,
    latest,
    officer_criteria,
    public_criteria,
)
from ..rules.programs import PROGRAMS
from ..rules.roles import ROLE_PROVINCE

public_router = APIRouter(prefix="/api/programs", tags=["program criteria"])
officer_router = APIRouter(prefix="/api/officer/programs", tags=["officer criteria"])


class CriteriaUpdate(BaseModel):
    announcement_date: str
    application_period: list[str]
    application_period_2: list[str] | None = None
    document_issue_rules: dict[str, dict[str, Any]] = PydanticField(default_factory=dict)
    document_issue_fallback: dict[str, Any] = PydanticField(default_factory=lambda: {"mode": "none"})
    document_date_bases: dict[str, str] = PydanticField(default_factory=dict)
    nhis_payment_months: list[str]
    nhis_acquisition_loss_years: int
    supplement: dict[str, Any] | None = None
    subsidy_catalog: list[dict[str, Any]] | None = None
    paper_forms: dict[str, bool] | None = None


def _program(code: str) -> None:
    if code not in PROGRAMS:
        raise HTTPException(404, "사업을 찾을 수 없습니다.")


def _date(value: str, label: str) -> date:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise HTTPException(400, f"{label}은 YYYY-MM-DD 형식이어야 합니다.")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(400, f"{label} 날짜가 올바르지 않습니다.") from None


def _validated(body: CriteriaUpdate, code: str) -> dict[str, Any]:
    _date(body.announcement_date, "기준일")
    if len(body.application_period) != 2:
        raise HTTPException(400, "신청 기간은 시작일과 종료일을 입력해 주세요.")
    period = [_date(value, "신청 기간") for value in body.application_period]
    if period[0] > period[1]:
        raise HTTPException(400, "신청 기간 시작일은 종료일보다 늦을 수 없습니다.")
    period_2: list[date] | None = None
    if body.application_period_2 is not None:
        if len(body.application_period_2) != 2:
            raise HTTPException(400, "2차 신청 기간은 시작일과 종료일을 입력해 주세요.")
        period_2 = [_date(value, "2차 신청 기간") for value in body.application_period_2]
        if period_2[0] > period_2[1]:
            raise HTTPException(400, "2차 신청 기간 시작일은 종료일보다 늦을 수 없습니다.")

    valid_modes = {"after_date", "after_notice", "within_days", "none"}
    rules = dict(body.document_issue_rules)
    rules["__fallback__"] = dict(body.document_issue_fallback)
    for key, rule in rules.items():
        mode = rule.get("mode")
        if mode not in valid_modes:
            raise HTTPException(400, f"{key}의 발급일 기준 방식이 올바르지 않습니다.")
        if mode == "after_date":
            _date(str(rule.get("date", "")), f"{key} 발급일 기준 날짜")
        elif mode == "within_days":
            days = rule.get("days")
            if not isinstance(days, int) or not 1 <= days <= 3650:
                raise HTTPException(400, f"{key}의 인정 일수는 1~3650일이어야 합니다.")
    valid_date_bases = {"issue_date", "payment_date", "interview_date", "exam_date", "none"}
    if any(value not in valid_date_bases for value in body.document_date_bases.values()):
        raise HTTPException(400, "서류 기준 날짜 종류가 올바르지 않습니다.")
    if not body.nhis_payment_months:
        raise HTTPException(400, "고지월은 1개 이상 지정해야 합니다.")
    months: list[str] = []
    today = date.today()
    for value in body.nhis_payment_months:
        match = re.fullmatch(r"(\d{4})-(0[1-9]|1[0-2])", value)
        if not match:
            raise HTTPException(400, "고지월은 YYYY-MM 형식이어야 합니다.")
        year, month = int(match.group(1)), int(match.group(2))
        if (year, month) > (today.year, today.month):
            raise HTTPException(400, "고지월에 미래 달은 지정할 수 없습니다.")
        if value not in months:
            months.append(value)
    months.sort()
    if not 1 <= body.nhis_acquisition_loss_years <= 10:
        raise HTTPException(400, "자격득실 포함 기간은 1~10년이어야 합니다.")
    supplement = body.supplement or default_criteria(code)["supplement"]
    allowed = supplement.get("allowed")
    days = supplement.get("days")
    if not isinstance(allowed, bool):
        raise HTTPException(400, "서류 보완 허용 여부가 올바르지 않습니다.")
    if allowed and (not isinstance(days, int) or not 1 <= days <= 365):
        raise HTTPException(400, "보완 기간은 1~365일이어야 합니다.")
    if not allowed:
        days = None
    catalog = body.subsidy_catalog
    if code == "job_package":
        if not catalog:
            catalog = default_criteria(code)["subsidy_catalog"]
        if len(catalog) != 4:
            raise HTTPException(400, "지원 항목은 네 종류를 모두 설정해야 합니다.")
        seen: set[str] = set()
        for item in catalog:
            key = item.get("item_type")
            if key not in {"interview", "suit", "photo", "certificate"} or key in seen:
                raise HTTPException(400, "지원 항목 종류가 중복되거나 올바르지 않습니다.")
            seen.add(str(key))
            if not str(item.get("label", "")).strip():
                raise HTTPException(400, "지원 항목 이름을 입력해 주세요.")
            if not isinstance(item.get("unit_cap"), int) or int(item["unit_cap"]) <= 0:
                raise HTTPException(400, "지원 한도는 1원 이상이어야 합니다.")
            if not isinstance(item.get("max_count"), int) or not 1 <= int(item["max_count"]) <= 20:
                raise HTTPException(400, "지원 횟수는 1~20회여야 합니다.")
            if not isinstance(item.get("actual_cost"), bool):
                raise HTTPException(400, "정액/실비 방식을 선택해 주세요.")
            if item.get("count_scope", "year") not in {"application", "year", "lifetime"}:
                raise HTTPException(400, "지원 횟수 범위가 올바르지 않습니다.")
            for doc in item.get("extra_docs", []):
                if doc.get("date_basis") not in {"issue_date", "payment_date", "interview_date", "exam_date", "none"}:
                    raise HTTPException(400, "서류 기준 날짜 종류가 올바르지 않습니다.")
    else:
        catalog = []
    default_paper_forms = default_criteria(code)["paper_forms"]
    paper_forms = {**default_paper_forms, **(body.paper_forms or {})}
    if set(paper_forms) != set(default_paper_forms) or any(not isinstance(value, bool) for value in paper_forms.values()):
        raise HTTPException(400, "종이 제출 허용 설정이 올바르지 않습니다.")
    return {
        "schema_version": CRITERIA_SCHEMA_VERSION,
        "announcement_date": body.announcement_date,
        "application_period": [value.isoformat() for value in period],
        "application_period_2": [value.isoformat() for value in period_2] if period_2 else None,
        "document_issue_rules": body.document_issue_rules,
        "document_issue_fallback": body.document_issue_fallback,
        "document_date_bases": body.document_date_bases,
        "nhis_payment_months": months,
        "nhis_acquisition_loss_years": body.nhis_acquisition_loss_years,
        "supplement": {"allowed": allowed, "days": days},
        "subsidy_catalog": catalog,
        "paper_forms": paper_forms,
    }


@public_router.get("/{code}/criteria")
def applicant_criteria(code: str) -> dict[str, Any]:
    _program(code)
    return public_criteria(latest(code))


@officer_router.get("/{code}/criteria")
def get_officer_criteria(code: str, role: str = Query(...)) -> dict[str, Any]:
    _program(code)
    try:
        from ..rules.roles import get_role

        get_role(role)
    except ValueError:
        raise HTTPException(400, "담당자 역할이 올바르지 않습니다.") from None
    rows = history(code)
    current = rows[0] if rows else latest(code)
    return {"current": officer_criteria(current), "history": [officer_criteria(row) for row in rows]}


@officer_router.put("/{code}/criteria")
def update_criteria(code: str, body: CriteriaUpdate, role: str = Query(...)) -> dict[str, Any]:
    _program(code)
    if role != ROLE_PROVINCE:
        raise HTTPException(403, "시·도 담당자만 심사 기준을 변경할 수 있습니다.")
    criteria = _validated(body, code)
    current = latest(code)
    row = ProgramCriteriaVersion(
        program_code=code,
        version=current.version + 1,
        criteria_json=criteria,
        changed_at=datetime.now(),
        changed_role=role,
    )
    with get_session() as session:
        session.add(row)
        session.commit()
        session.refresh(row)
    return officer_criteria(row)
