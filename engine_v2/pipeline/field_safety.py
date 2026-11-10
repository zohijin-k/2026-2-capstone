"""공통 추출 결과 안전 검사."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any


HEADER_LABELS = (
    "가입자구분", "자격취득일", "자격상실일", "사업장명칭", "가입자성명",
    "주민등록번호", "주민번호", "생년월일", "납부자번호",
    "발급년월일", "발급일자", "발행일자", "발급일", "발행일", "성명",
    "고지금액", "납부금액", "보험료", "가입자", "가구원", "월별", "년월",
)
_NORMALIZED_LABELS = tuple(sorted({re.sub(r"\s+", "", item) for item in HEADER_LABELS}, key=len, reverse=True))


def _normalize(value: str) -> str:
    return re.sub(r"[\s:：·,，|/()（）._-]+", "", value).strip()


@lru_cache(maxsize=512)
def _labels_only(value: str) -> bool:
    if not value:
        return False
    if value in _NORMALIZED_LABELS:
        return True
    # OCR이 머리표 여러 개를 공백 없이 붙여 읽은 경우도 모두 머리표면 막는다.
    reachable = {0}
    for start in range(len(value)):
        if start not in reachable:
            continue
        for label in _NORMALIZED_LABELS:
            if value.startswith(label, start):
                reachable.add(start + len(label))
    return len(value) in reachable


def is_header_only_value(value: Any) -> bool:
    """값이 알려진 머리표 하나 또는 머리표만 이어 붙인 문자열인지 확인한다."""
    return isinstance(value, str) and _labels_only(_normalize(value))


def remove_header_only_fields(fields: dict[str, Any]) -> list[str]:
    """추출 필드 중 머리표 문자열만 들어간 값을 제거하고 제거한 키를 돌려준다."""
    removed = []
    for key, field in list(fields.items()):
        value = getattr(field, "value", field)
        if is_header_only_value(value):
            del fields[key]
            removed.append(key)
    return removed
