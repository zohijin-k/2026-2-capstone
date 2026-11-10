"""건강보험 자격확인서 가구원 증거를 읽고 신청서끼리 대조한다."""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from .doc_types import DocType


def _normalized_name(value: Any) -> str:
    return re.sub(r"\s+", "", value) if isinstance(value, str) else ""


def _normalized_birth(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    digits = re.sub(r"\D", "", value)
    if len(digits) != 8:
        return ""
    try:
        return date(int(digits[:4]), int(digits[4:6]), int(digits[6:8])).isoformat()
    except ValueError:
        return ""


def parse_household_members(value: Any) -> list[dict[str, str]] | None:
    """가구원목록을 정규화한다. 하나라도 식별 정보가 불완전하면 None."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return None
    if not isinstance(value, list) or not value:
        return None

    members: dict[tuple[str, str], dict[str, str]] = {}
    for item in value:
        if not isinstance(item, dict):
            return None
        name = _normalized_name(item.get("성명"))
        birth = _normalized_birth(item.get("생년월일"))
        if not name or not birth:
            return None
        members[(name, birth)] = {"성명": name, "생년월일": birth}
    return list(members.values())


def qualification_members(documents: list[dict[str, Any]]) -> list[dict[str, str]] | None:
    """건강보험 자격확인서의 가구원 목록만 반환한다."""
    qualification = next(
        (row for row in documents if row.get("doc_type") == str(DocType.NHIS_QUALIFICATION)),
        None,
    )
    if qualification is None:
        return None
    fields = qualification.get("fields") or {}
    return parse_household_members(fields.get("가구원목록"))


def overlap_members(
    left: list[dict[str, str]] | None,
    right: list[dict[str, str]] | None,
) -> list[dict[str, str]]:
    """주소는 보지 않고 이름·생년월일이 모두 같은 가구원만 찾는다."""
    if not left or not right:
        return []
    right_keys = {(row["성명"], row["생년월일"]) for row in right}
    return [row for row in left if (row["성명"], row["생년월일"]) in right_keys]
