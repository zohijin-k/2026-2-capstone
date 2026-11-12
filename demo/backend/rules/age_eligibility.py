"""Inclusive program age eligibility, separate from age scoring points."""
from dataclasses import dataclass
from datetime import date
import re
from typing import Any

from .facts import parse_ymd
from .programs import ProgramConfig


@dataclass(frozen=True)
class AgeEligibilityResult:
    status: str
    reason_code: str | None
    basis: str
    birth_date: date | None

    def as_dict(self) -> dict[str, object]:
        return {"status": self.status, "reason_code": self.reason_code, "basis": self.basis,
                "birth_date": self.birth_date.isoformat() if self.birth_date else None}


def _birth_date(value: Any) -> date | None:
    # Birth dates are full dates, not timestamps or strings with trailing residue.
    # Never turn a malformed submitted value into a certain age rejection.
    if isinstance(value, str):
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            return None
    elif isinstance(value, dict):
        for key in ("y", "m", "d"):
            part = value.get(key)
            if type(part) is not int and not (isinstance(part, str) and re.fullmatch(r"[0-9]+", part)):
                return None
    else:
        return None
    try:
        return parse_ymd(value)
    except OverflowError:
        return None


def assess_age(program: ProgramConfig, form_birth: Any, identity: dict[str, Any] | None = None) -> AgeEligibilityResult:
    """Use submitted birth and, when present, compare the immutable identity value."""
    birth = _birth_date(form_birth)
    if birth is None:
        return AgeEligibilityResult("NEEDS_REVIEW", "AGE_UNDETERMINED",
                                    "신청서 생년월일이 없거나 읽을 수 없어 연령 요건을 판정할 수 없습니다. 담당자 확인이 필요합니다.", None)
    if identity and "birth" in identity:
        verified_birth = _birth_date(identity["birth"])
        if verified_birth is None or verified_birth != birth:
            return AgeEligibilityResult("NEEDS_REVIEW", "AGE_IDENTITY_MISMATCH",
                                        "신청서 생년월일과 본인인증 생년월일이 일치하지 않거나 본인인증 값을 읽지 못했습니다. 담당자 확인이 필요합니다.", birth)
    low, high = program.birth_range
    basis = (f"신청서 생년월일 {birth.isoformat()} · 허용 출생일 "
             f"{low.isoformat()}~{high.isoformat()} (양 끝 포함)")
    if not low <= birth <= high:
        return AgeEligibilityResult("FAIL", "AGE_OUT_OF_RANGE", basis + " → 연령 요건 범위 밖", birth)
    return AgeEligibilityResult("PASS", None, basis + " → 연령 요건 충족", birth)
