"""사업별로 버전 관리하는 심사 기준."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlmodel import select

from ..models import Application, ProgramCriteriaVersion, get_session
from .programs import PROGRAMS

CRITERIA_SCHEMA_VERSION = 2


def default_criteria(program_code: str) -> dict[str, Any]:
    program = PROGRAMS[program_code]
    if program_code == "double_savings":
        fallback = {"mode": "after_notice"}
        rules = {
            key: {"mode": "after_notice"} for key in (
                "resident_abstract", "nhis_payment", "nhis_qualification",
                "nhis_acquisition_loss", "work_proof", "work_proof_1", "work_proof_2",
            )
        }
    else:
        fallback = {"mode": "after_date", "date": program.document_cutoff.isoformat()}
        rules = {"resident_abstract": {"mode": "after_date", "date": program.document_cutoff.isoformat()}}
    doc_keys = (
        "resident_abstract", "nhis_payment", "nhis_qualification", "nhis_acquisition_loss",
        "admin_info_consent", "work_proof", "work_proof_1", "work_proof_2",
        "interview_confirmation", "receipt", "exam_result", "labor_contract",
        "insurance_4", "daily_work_record", "biz_reg_proof", "farm_biz_cert",
        "fishery_biz_cert", "job_search_plan",
    )
    for key in doc_keys:
        rules.setdefault(key, dict(fallback))
    return {
        "schema_version": CRITERIA_SCHEMA_VERSION,
        "announcement_date": program.announcement_date.isoformat(),
        "application_period": [d.isoformat() for d in program.apply_period],
        "application_period_2": [d.isoformat() for d in program.apply_period_2] if program.apply_period_2 else None,
        "document_issue_rules": rules,
        "document_issue_fallback": fallback,
        "nhis_payment_months": ["2025-10", "2025-11", "2025-12"],
        "nhis_acquisition_loss_years": 5,
    }


def read_criteria(row: ProgramCriteriaVersion) -> dict[str, Any]:
    """읽을 때만 저장 형식을 현재 스키마로 보정한다. DB 스냅샷은 변경하지 않는다."""
    defaults = default_criteria(row.program_code)
    stored = row.criteria_json if isinstance(row.criteria_json, dict) else {}
    merged = {**defaults, **stored, "schema_version": CRITERIA_SCHEMA_VERSION}

    # 구버전에서 문서별 규칙이 일부만 저장된 경우 기본 문서 규칙도 유지한다.
    merged["document_issue_rules"] = {
        **defaults["document_issue_rules"],
        **(stored.get("document_issue_rules") or {}),
    }
    merged["document_issue_fallback"] = {
        **defaults["document_issue_fallback"],
        **(stored.get("document_issue_fallback") or {}),
    }
    return merged


def ensure_defaults() -> None:
    """새 DB에는 v1을 만들고, 과거 신청서는 현재 최초 버전에 연결한다."""
    with get_session() as session:
        for code in PROGRAMS:
            latest = session.exec(
                select(ProgramCriteriaVersion)
                .where(ProgramCriteriaVersion.program_code == code)
                .order_by(ProgramCriteriaVersion.version.desc())
            ).first()
            if latest is None:
                session.add(ProgramCriteriaVersion(
                    program_code=code, version=1, criteria_json=default_criteria(code),
                    changed_role="system",
                ))
        session.commit()
        versions = {
            code: session.exec(
                select(ProgramCriteriaVersion)
                .where(ProgramCriteriaVersion.program_code == code)
                .order_by(ProgramCriteriaVersion.version.desc())
            ).first().version
            for code in PROGRAMS
        }
        for app in session.exec(select(Application).where(Application.criteria_version.is_(None))).all():
            app.criteria_version = versions.get(app.program_code, 1)
            session.add(app)
        session.commit()


def history(program_code: str) -> list[ProgramCriteriaVersion]:
    with get_session() as session:
        return list(session.exec(
            select(ProgramCriteriaVersion)
            .where(ProgramCriteriaVersion.program_code == program_code)
            .order_by(ProgramCriteriaVersion.version.desc())
        ).all())


def latest(program_code: str) -> ProgramCriteriaVersion:
    rows = history(program_code)
    if rows:
        return rows[0]
    # API tests may create a database without going through FastAPI lifespan.
    row = ProgramCriteriaVersion(program_code=program_code, version=1,
                                 criteria_json=default_criteria(program_code), changed_role="system")
    with get_session() as session:
        session.add(row)
        session.commit()
        session.refresh(row)
    return row


def for_application(app: Application) -> ProgramCriteriaVersion:
    if app.criteria_version is None:
        return latest(app.program_code)
    with get_session() as session:
        row = session.exec(
            select(ProgramCriteriaVersion)
            .where(ProgramCriteriaVersion.program_code == app.program_code)
            .where(ProgramCriteriaVersion.version == app.criteria_version)
        ).first()
    return row or latest(app.program_code)


def issue_rule_for(criteria: dict[str, Any], slot_key: str) -> dict[str, Any]:
    rules = criteria.get("document_issue_rules") or {}
    if slot_key in rules:
        return rules[slot_key]
    # Work slots and itemized expense slots include a sequence number. Match their
    # stable document family setting so new rows follow the same rule.
    for key, rule in rules.items():
        if key == "work_proof" and slot_key.startswith("work_proof_"):
            return rule
        if key in {"confirmation", "receipt", "photo", "exam"} and slot_key.endswith(f"_{key}"):
            return rule
    return criteria.get("document_issue_fallback", {"mode": "none"})


def issue_bounds(criteria: dict[str, Any], slot_key: str, application_date: date) -> tuple[date | None, date | None]:
    rule = issue_rule_for(criteria, slot_key)
    mode = rule.get("mode", "none")
    if mode == "after_notice":
        return date.fromisoformat(criteria["announcement_date"]), None
    if mode == "after_date":
        return date.fromisoformat(rule["date"]), None
    if mode == "within_days":
        return application_date - timedelta(days=int(rule["days"])), application_date
    return None, None


def issue_rule_label(criteria: dict[str, Any], slot_key: str) -> str:
    rule = issue_rule_for(criteria, slot_key)
    mode = rule.get("mode", "none")
    if mode == "after_date":
        return f"{rule.get('date', '')} 이후 발급"
    if mode == "after_notice":
        return f"{criteria['announcement_date']} 공고일 이후 발급"
    if mode == "within_days":
        return f"신청일 기준 {int(rule.get('days', 0))}일 이내 발급"
    return "발급일 기준 없음"


def public_criteria(row: ProgramCriteriaVersion) -> dict[str, Any]:
    data = read_criteria(row)
    return {
        "version": row.version,
        "schema_version": data["schema_version"],
        "announcement_date": data["announcement_date"],
        "application_period": data["application_period"],
        "application_period_2": data.get("application_period_2"),
        "document_issue_rules": data.get("document_issue_rules", {}),
        "document_issue_fallback": data.get("document_issue_fallback", {"mode": "none"}),
        "nhis_payment_months": data["nhis_payment_months"],
        "nhis_acquisition_loss_years": data["nhis_acquisition_loss_years"],
    }


def officer_criteria(row: ProgramCriteriaVersion) -> dict[str, Any]:
    return {
        **public_criteria(row),
        "changed_at": row.changed_at.isoformat(timespec="seconds"),
        "changed_role": row.changed_role,
    }
