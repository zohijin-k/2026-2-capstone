"""취업지원패키지 지원 항목 · 실비 계산 (R6.1/R6.2).

사업계획서 「Ⅲ. 세부사업계획 3. 지원금 지급 — 지원내용」 표를 그대로 옮긴 것이다.

    구분      내용                              지원금액          비고
    면 접 비  도내 기업·기관 등 면접비 지원      50,000원(회당)    최대 2회
    정 장 비  면접용 정장 대여비 지원            50,000원(실비)    최대 2회
    면접사진  면접사진 촬영비 지원(증명사진)     20,000원(실비)    1회
    자 격 증  자격증 응시료 지원                 50,000원(실비)    최대 2회

여기서 갈리는 것이 하나 있다. **면접비만 정액**이다("회당"). 영수증을 받지 않고
면접확인서만으로 회당 5만원을 지급한다. 나머지 3종은 "(실비)"라서 영수증 금액과
한도 중 **작은 값**을 지급한다. 정장 35,000원이면 35,000원, 70,000원이면 50,000원.

이 모듈은 DB·HTTP를 모른다. `rules/scoring.py`와 같은 이유다 — 계산이 순수해야
검증 스크립트가 화면 없이 숫자를 확인할 수 있다.
"""

from dataclasses import dataclass, field
from enum import StrEnum

from .doc_types import DocType


class SubsidyType(StrEnum):
    INTERVIEW = "interview"
    SUIT = "suit"
    PHOTO = "photo"
    CERTIFICATE = "certificate"


@dataclass(frozen=True)
class ExtraDoc:
    """항목을 고르면 따라붙는 추가서류 1종.

    `suffix`가 업로드 슬롯 키의 꼬리다. 같은 서류(면접확인서)가 면접비와 정장비
    양쪽에 붙으므로, 슬롯은 `항목_회차_꼬리`로 만들어 서로 겹치지 않게 한다.
    """

    suffix: str
    doc_type: DocType
    label: str
    #: 이 자리에 인정되는 서류가 여럿인 경우 (응시확인서 **또는** 성적표).
    accepted: tuple[DocType, ...] = ()
    #: 판독 결과에 반드시 있어야 하는 필드. 없으면 부적합이다.
    required_fields: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ItemLimit:
    key: SubsidyType
    label: str
    #: 사업계획서 '내용' 칸 원문.
    description: str
    unit_cap: int
    max_count: int
    #: True면 실비(영수증 금액과 한도 중 작은 값), False면 정액.
    actual_cost: bool
    extra_docs: tuple[ExtraDoc, ...]
    note: str = ""

    @property
    def needs_receipt(self) -> bool:
        return self.actual_cost

    @property
    def max_amount(self) -> int:
        return self.unit_cap * self.max_count


#: 신청서류 표의 추가서류 항목. 공통서류(신청서·초본·통장사본)는
#: `rules/required_docs.py`가 따로 붙인다.
_INTERVIEW_CONFIRMATION = ExtraDoc(
    suffix="confirmation",
    doc_type=DocType.INTERVIEW_CONFIRMATION,
    label="면접확인서",
    notes=("면접을 본 기업·기관에서 발급받습니다.",),
)

_RECEIPT = ExtraDoc(
    suffix="receipt",
    doc_type=DocType.PAYMENT_RECEIPT,
    label="결제영수증",
    required_fields=("결제금액",),
    notes=("영수증 금액과 지원 한도 중 작은 금액을 지급합니다.",),
)

LIMITS: dict[SubsidyType, ItemLimit] = {
    SubsidyType.INTERVIEW: ItemLimit(
        key=SubsidyType.INTERVIEW,
        label="면접비",
        description="도내 기업·기관 등 면접비 지원",
        unit_cap=50_000,
        max_count=2,
        actual_cost=False,
        extra_docs=(_INTERVIEW_CONFIRMATION,),
        note="회당 정액 지급입니다. 영수증 없이 면접확인서만 올리면 됩니다.",
    ),
    SubsidyType.SUIT: ItemLimit(
        key=SubsidyType.SUIT,
        label="면접정장비",
        description="면접용 정장 대여비 지원",
        unit_cap=50_000,
        max_count=2,
        actual_cost=True,
        extra_docs=(_INTERVIEW_CONFIRMATION, _RECEIPT),
        note="실비 지급입니다. 대여비가 한도보다 적으면 결제한 금액만 지급됩니다.",
    ),
    SubsidyType.PHOTO: ItemLimit(
        key=SubsidyType.PHOTO,
        label="면접사진비",
        description="면접사진 촬영비 지원(증명사진)",
        unit_cap=20_000,
        max_count=1,
        actual_cost=True,
        extra_docs=(
            ExtraDoc(
                suffix="photo",
                doc_type=DocType.ID_PHOTO_COPY,
                label="면접용 사진사본",
            ),
            _RECEIPT,
        ),
        note="실비 지급이며 1회만 지원됩니다.",
    ),
    SubsidyType.CERTIFICATE: ItemLimit(
        key=SubsidyType.CERTIFICATE,
        label="자격증 응시료",
        description="자격증 응시료 지원",
        unit_cap=50_000,
        max_count=2,
        actual_cost=True,
        extra_docs=(
            ExtraDoc(
                suffix="exam",
                doc_type=DocType.EXAM_CONFIRMATION,
                label="응시확인서 또는 성적표",
                accepted=(DocType.EXAM_CONFIRMATION, DocType.EXAM_TRANSCRIPT),
                # 사업계획서 신청서류 표의 괄호 주석: "(응시일 표기 필수)"
                required_fields=("응시일",),
                notes=("응시확인서와 성적표 중 하나만 올리면 됩니다.",),
                warnings=(
                    "응시일이 표기된 서류여야 합니다. 응시일이 없으면 인정되지 않습니다.",
                ),
            ),
            _RECEIPT,
        ),
        note="실비 지급입니다. 응시확인서·성적표에 응시일이 찍혀 있어야 합니다.",
    ),
}

#: 화면 표시 순서. 사업계획서 표 순서를 그대로 따른다.
ITEM_ORDER: tuple[SubsidyType, ...] = (
    SubsidyType.INTERVIEW,
    SubsidyType.SUIT,
    SubsidyType.PHOTO,
    SubsidyType.CERTIFICATE,
)

#: 성과목표 (사업계획서 「4. 성과목표」). 선착순 진행률 표시에 쓴다.
PERFORMANCE_TARGETS: dict[SubsidyType, int] = {
    SubsidyType.INTERVIEW: 330,
    SubsidyType.SUIT: 20,
    SubsidyType.PHOTO: 150,
    SubsidyType.CERTIFICATE: 400,
}


def get_limit(item_type: str | SubsidyType) -> ItemLimit:
    try:
        return LIMITS[SubsidyType(item_type)]
    except ValueError:
        raise ValueError(f"알 수 없는 지원 항목: {item_type}") from None


# ---------------------------------------------------------------- 선택 · 계산


@dataclass
class Selection:
    """신청자가 고른 항목 1종. `receipts`는 회차별 영수증 금액(원)."""

    item_type: SubsidyType
    count: int = 1
    receipts: list[int | None] = field(default_factory=list)

    def receipt_at(self, index: int) -> int | None:
        """1-based 회차의 영수증 금액."""
        if 0 < index <= len(self.receipts):
            return self.receipts[index - 1]
        return None


@dataclass
class GrantLine:
    """지급 계산 한 줄. 신청자 화면과 담당자 화면이 그대로 읽는다."""

    item_type: str
    label: str
    index: int
    unit_cap: int
    actual_cost: bool
    receipt_amount: int | None
    granted_amount: int
    #: 계산 근거 한 줄. "영수증 70,000원 > 한도 50,000원 → 50,000원 지급"
    calculation: str
    #: 아직 지급액이 확정되지 않은 줄 (영수증 금액 미입력 등).
    pending: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "item_type": self.item_type,
            "label": self.label,
            "index": self.index,
            "unit_cap": self.unit_cap,
            "actual_cost": self.actual_cost,
            "receipt_amount": self.receipt_amount,
            "granted_amount": self.granted_amount,
            "calculation": self.calculation,
            "pending": self.pending,
        }


@dataclass
class Estimate:
    lines: list[GrantLine]
    total_granted: int
    #: 횟수 상한 초과처럼 입력을 조정한 사실. 화면에 그대로 띄운다.
    warnings: list[str] = field(default_factory=list)
    #: 아직 확정되지 않은 줄이 있는가.
    pending: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "lines": [line.as_dict() for line in self.lines],
            "total_granted": self.total_granted,
            "warnings": self.warnings,
            "pending": self.pending,
        }


def _won(value: int) -> str:
    return f"{value:,}원"


def granted_amount(item_type: str | SubsidyType, receipt_amount: int | None) -> int:
    """실지급액 (R6.2).

    정액 항목(면접비)은 영수증과 무관하게 회당 한도를 지급한다. 실비 항목은
    영수증 금액과 한도 중 작은 값이며, 영수증 금액이 없으면 0이다.
    """
    limit = get_limit(item_type)
    if not limit.actual_cost:
        return limit.unit_cap
    if receipt_amount is None or receipt_amount <= 0:
        return 0
    return min(int(receipt_amount), limit.unit_cap)


def clamp_count(item_type: str | SubsidyType, count: int) -> int:
    limit = get_limit(item_type)
    return max(0, min(int(count), limit.max_count))


def estimate(selections: list[Selection]) -> Estimate:
    """선택한 항목들의 예상 지원금.

    항목을 복수로 고를 수 있고(사업계획서 "복수선택가능"), 항목마다 회차가 따로
    붙는다. 회차별로 한 줄씩 계산해 근거 문장을 남긴다 — 합계만 보여주면
    신청자는 "왜 7만원을 냈는데 5만원인가"를 다시 묻는다.
    """
    lines: list[GrantLine] = []
    warnings: list[str] = []

    for selection in selections:
        limit = get_limit(selection.item_type)
        count = clamp_count(selection.item_type, selection.count)
        if selection.count > limit.max_count:
            warnings.append(
                f"{limit.label}은(는) 최대 {limit.max_count}회까지 지원됩니다. "
                f"{selection.count}회 신청 → {limit.max_count}회로 조정했습니다."
            )
        for index in range(1, count + 1):
            receipt = selection.receipt_at(index)
            amount = granted_amount(selection.item_type, receipt)
            if not limit.actual_cost:
                calculation = f"정액 {_won(limit.unit_cap)}(회당) → {_won(amount)} 지급"
                pending = False
            elif receipt is None or receipt <= 0:
                calculation = "결제영수증 금액을 입력하면 지급액이 계산됩니다."
                pending = True
            elif receipt > limit.unit_cap:
                calculation = (
                    f"영수증 {_won(receipt)} > 한도 {_won(limit.unit_cap)} "
                    f"→ {_won(amount)} 지급"
                )
                pending = False
            else:
                calculation = (
                    f"영수증 {_won(receipt)} ≤ 한도 {_won(limit.unit_cap)} "
                    f"→ {_won(amount)} 지급"
                )
                pending = False

            lines.append(
                GrantLine(
                    item_type=str(limit.key),
                    label=f"{limit.label} {index}회차",
                    index=index,
                    unit_cap=limit.unit_cap,
                    actual_cost=limit.actual_cost,
                    receipt_amount=receipt,
                    granted_amount=amount,
                    calculation=calculation,
                    pending=pending,
                )
            )

    return Estimate(
        lines=lines,
        total_granted=sum(line.granted_amount for line in lines),
        warnings=warnings,
        pending=any(line.pending for line in lines),
    )


def parse_selections(raw: list[dict[str, object]]) -> list[Selection]:
    """API 입력 → `Selection` 목록. 회차가 0이면 고르지 않은 것으로 본다."""
    selections: list[Selection] = []
    for entry in raw:
        item_type = SubsidyType(str(entry.get("item_type")))
        count = int(entry.get("count") or 0)
        if count <= 0:
            continue
        receipts_raw = entry.get("receipts") or []
        receipts: list[int | None] = []
        if isinstance(receipts_raw, list):
            for value in receipts_raw:
                if value is None or value == "":
                    receipts.append(None)
                else:
                    try:
                        receipts.append(int(value))
                    except (TypeError, ValueError):
                        receipts.append(None)
        selections.append(Selection(item_type=item_type, count=count, receipts=receipts))
    return selections


def catalog() -> list[dict[str, object]]:
    """화면이 읽는 지원 항목 목록. 금액·횟수·추가서류가 전부 여기서 나간다."""
    rows: list[dict[str, object]] = []
    for key in ITEM_ORDER:
        limit = LIMITS[key]
        rows.append(
            {
                "item_type": str(key),
                "label": limit.label,
                "description": limit.description,
                "unit_cap": limit.unit_cap,
                "max_count": limit.max_count,
                "actual_cost": limit.actual_cost,
                "needs_receipt": limit.needs_receipt,
                "max_amount": limit.max_amount,
                "note": limit.note,
                "amount_label": (
                    f"{_won(limit.unit_cap)}(실비)"
                    if limit.actual_cost
                    else f"{_won(limit.unit_cap)}(회당)"
                ),
                "count_label": (
                    "1회" if limit.max_count == 1 else f"최대 {limit.max_count}회"
                ),
                "extra_docs": [d.label for d in limit.extra_docs],
                "performance_target": PERFORMANCE_TARGETS.get(key),
            }
        )
    return rows
