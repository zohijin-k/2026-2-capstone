"""본인 대조 — 업로드 서류가 '본인인증된 신청자'의 것인지.

기준은 본인인증 결과(`Application.identity_json`)다. 신청서에 손으로 적은 성명·생년월일은
기준이 될 수 없다 — 담당자가 신청자 입력값을 믿지 않는 이유가 바로 이것이다.

대조 항목은 서류에서 읽은 **성명 + 생년월일**이다. 동명이인이 있어 성명만으로는 부족하다.
서류에 해당 항목이 없으면(판독기가 아직 성명을 뽑지 않는 서류) 대조하지 않는다.
"""

import re
import json
from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class Identity:
    name: str
    birth: date


def norm_name(value: str | None) -> str:
    """공백을 지운 비교용 성명. 서류 판독값은 '홍 길동'처럼 띄어 읽히기도 한다."""
    return re.sub(r"\s+", "", value or "")


def identity_of(identity_json: dict[str, Any] | None) -> Identity | None:
    """저장된 본인인증 결과 → 대조 기준. 인증 전이면 None (대조하지 않는다)."""
    if not identity_json:
        return None
    try:
        return Identity(norm_name(identity_json["name"]), date.fromisoformat(identity_json["birth"]))
    except (KeyError, TypeError, ValueError):
        return None


def compare(identity: Identity, fields: dict[str, str]) -> tuple[list[str], list[str]]:
    """서류 판독값과 대조한다. 반환: (대조한 항목, 다른 항목)."""
    checked: list[str] = []
    mismatched: list[str] = []

    name = norm_name(fields.get("성명"))
    if name:
        checked.append("성명")
        if name != identity.name:
            mismatched.append("성명")

    raw_birth = (fields.get("생년월일") or "").strip()
    if raw_birth:
        try:
            birth = date.fromisoformat(raw_birth[:10])
        except ValueError:
            birth = None
        if birth is not None:
            checked.append("생년월일")
            if birth != identity.birth:
                mismatched.append("생년월일")

    return checked, mismatched


def nhis_subscriber_assessment(
    identity: Identity,
    document_type: str,
    fields: dict[str, str],
    related_documents: list[tuple[str, dict[str, str]]],
) -> tuple[str, str, str] | None:
    """건강보험 가입자 명의를 판정한다. 반환값은 (사유코드, 심각도, 담당자 근거)."""
    own_name = norm_name(fields.get("성명") or fields.get("가입자성명"))
    own_birth = fields.get("생년월일") or fields.get("가입자생년월일") or ""
    if own_name == identity.name and own_birth:
        try:
            if date.fromisoformat(own_birth[:10]) == identity.birth:
                return None
        except ValueError:
            pass
    elif own_name == identity.name and not own_birth:
        # 현재 판독기는 일부 자격확인서에서 성명만 읽으므로 기존의 본인 명의 인정은 유지한다.
        return None

    if not own_name:
        return (
            "NHIS_SUBSCRIBER_IDENTITY_REVIEW", "NEEDS_REVIEW",
            "건강보험 서류의 가입자 성명을 읽지 못했습니다.",
        )

    payment_type = "건강보험료납부확인서"
    qualification_type = "건강보험자격확인서"
    qualification = next((f for t, f in related_documents if t == qualification_type), None)
    payment = next((f for t, f in related_documents if t == payment_type), None)
    if document_type == payment_type and qualification is None:
        return (
            "NHIS_SUBSCRIBER_IDENTITY_REVIEW", "NEEDS_REVIEW",
            f"가입자 '{own_name}' 명의입니다. 건강보험 자격확인서가 제출되지 않아 피부양자 관계를 확인하지 못했습니다.",
        )
    if qualification is None or payment is None:
        return (
            "NHIS_SUBSCRIBER_IDENTITY_REVIEW", "NEEDS_REVIEW",
            f"가입자 '{own_name}' 명의입니다. 납부확인서와 자격확인서를 함께 확인해야 합니다.",
        )

    payment_name = norm_name(payment.get("성명") or payment.get("가입자성명"))
    qualification_name = norm_name(qualification.get("성명") or qualification.get("가입자성명"))
    if not payment_name or not qualification_name:
        return (
            "NHIS_SUBSCRIBER_IDENTITY_REVIEW", "NEEDS_REVIEW",
            "납부확인서 또는 자격확인서에서 가입자 성명을 읽지 못했습니다.",
        )
    payment_birth = payment.get("생년월일") or payment.get("가입자생년월일") or ""
    qualification_birth = qualification.get("생년월일") or qualification.get("가입자생년월일") or ""
    birth_differs = bool(payment_birth and qualification_birth and payment_birth[:10] != qualification_birth[:10])
    if payment_name != qualification_name or birth_differs:
        return (
            "NHIS_SUBSCRIBER_IDENTITY_REVIEW", "NEEDS_REVIEW",
            f"납부확인서 가입자 '{payment_name}'와 자격확인서 가입자 '{qualification_name}'가 일치하지 않습니다.",
        )

    raw_members = qualification.get("가구원목록")
    try:
        members = json.loads(raw_members) if isinstance(raw_members, str) else raw_members
    except (ValueError, TypeError):
        members = None
    if not isinstance(members, list):
        return (
            "NHIS_SUBSCRIBER_IDENTITY_REVIEW", "NEEDS_REVIEW",
            f"가입자 '{payment_name}' 명의이나 자격확인서 가구원 목록을 판독하지 못했습니다.",
        )

    applicant_found = False
    for member in members:
        if not isinstance(member, dict):
            continue
        member_name = norm_name(str(member.get("성명") or member.get("name") or ""))
        member_birth = str(member.get("생년월일") or member.get("birth") or "")
        try:
            parsed_birth = date.fromisoformat(member_birth[:10])
        except ValueError:
            continue
        if member_name == identity.name and parsed_birth == identity.birth:
            applicant_found = True
            break
    if not applicant_found:
        return (
            "NHIS_SUBSCRIBER_IDENTITY_REVIEW", "NEEDS_REVIEW",
            f"가입자 '{payment_name}' 명의이나 자격확인서 가구원 목록에서 본인 정보를 확인하지 못했습니다.",
        )

    return (
        "NHIS_DEPENDENT_INSURED_PERSON", "INFO",
        f"건강보험 가입자 명의(피부양자): '{payment_name}'. 납부확인서와 자격확인서의 가입자명이 일치하고, 자격확인서 가구원 목록의 성명·생년월일이 본인인증 정보와 일치합니다.",
    )
