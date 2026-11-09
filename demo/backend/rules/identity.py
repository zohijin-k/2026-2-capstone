"""본인 대조 — 업로드 서류가 '본인인증된 신청자'의 것인지.

기준은 본인인증 결과(`Application.identity_json`)다. 신청서에 손으로 적은 성명·생년월일은
기준이 될 수 없다 — 담당자가 신청자 입력값을 믿지 않는 이유가 바로 이것이다.

대조 항목은 서류에서 읽은 **성명 + 생년월일**이다. 동명이인이 있어 성명만으로는 부족하다.
서류에 해당 항목이 없으면(판독기가 아직 성명을 뽑지 않는 서류) 대조하지 않는다.
"""

import re
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
