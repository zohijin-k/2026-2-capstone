"""자가진단 채점 (서식2 / 취업패키지 축소판).

두배적금은 서식2 8문항이다. 하나라도 "아니오"면 신청 자격이 없다.
취업지원패키지는 사업계획서의 자격요건이 **나이와 거주지뿐**이라(「2. 서류심사 —
신청자 자격요건 검토(나이, 거주지 등)」) 2문항으로 줄어든다. 문항 수가 사업
설정에서 나오므로 화면은 사업 코드로 분기하지 않는다.

부적격 사유와 대안을 함께 돌려주는 것이 이 모듈의 핵심이다 — 콜센터 상담
3,073건 중 38%가 자격요건 문의였고, 안내가 없어서가 아니라 신청자가 스스로
확인할 방법이 없어서 반복됐다.

문항 본문은 프론트(`forms/form2-model.ts`)가 원문 그대로 들고 있다. 여기서는
판정과 사유만 다룬다.
"""

from dataclasses import dataclass

from .programs import DOUBLE_SAVINGS, JOB_PACKAGE


@dataclass(frozen=True)
class CheckItem:
    """문항 1개의 판정 정보."""

    no: int
    #: "아니오"일 때 보여줄 부적격 사유.
    reason: str
    #: 대안 안내. 없으면 빈 문자열.
    alternative: str = ""


#: 1번 문항에서 막힌 기초생활수급자에게는 더 유리한 사업이 따로 있다.
#: 시행지침이 직접 언급하는 내용이라 안내에 포함한다.
BASIC_LIVELIHOOD_ALTERNATIVE = (
    "기초생활수급자 및 법정 차상위계층은 보건복지부 청년내일저축계좌 대상으로, "
    "해당 사업의 혜택이 더 큽니다(3년간 10만원 적립 시 1:3 정부매칭으로 약 1,440만원 수령)."
)

DOUBLE_SAVINGS_ITEMS: tuple[CheckItem, ...] = (
    CheckItem(
        1,
        "이 사업은 공고일(2026. 3. 3.) 기준 주민등록상 주소지가 전북특별자치도인 청년만 신청할 수 있습니다.",
        "거주하시는 시·도의 청년 자산형성 지원사업을 확인해 보세요.",
    ),
    CheckItem(
        2,
        "1986. 1. 1. ~ 2007. 12. 31. 출생자만 신청할 수 있습니다(2025. 12. 31. 기준 만 18~39세).",
    ),
    CheckItem(
        3,
        "근로자는 2025. 10. 3. 이전부터 주 15시간 이상 계속 근로, "
        "사업자는 2025. 9. 3. 이전 개업 및 3개월(90일) 이상 운영 중이어야 합니다.",
    ),
    CheckItem(
        4,
        "근로확인서류(4대보험 가입내역 확인서 등 5종 중 1부)를 제출하지 못하면 자격을 확인할 수 없습니다.",
        "4대사회보험 정보연계센터·고용산재보험 토탈서비스·정부24에서 발급 가능한지 먼저 확인해 보세요.",
    ),
    CheckItem(
        5,
        "적금 계좌는 기초지자체 명의로 일괄 개설됩니다. 이 조건에 동의해야 참여할 수 있습니다.",
    ),
    CheckItem(6, "제외 대상 확인에 동의해야 신청할 수 있습니다.", BASIC_LIVELIHOOD_ALTERNATIVE),
    CheckItem(
        7,
        "가구 기준 중위소득 140% 이하만 신청할 수 있습니다. "
        "건강보험 자격확인서상 가구원수와 납부확인서상 고지금액('25.10~12월 평균)으로 판정합니다.",
    ),
    CheckItem(8, "중도해지 사유를 확인해야 신청할 수 있습니다."),
)

#: 취업지원패키지 축소판. 소득·근로·계좌명의 문항이 통째로 사라진다.
JOB_PACKAGE_ITEMS: tuple[CheckItem, ...] = (
    CheckItem(
        1,
        "이 사업은 전북특별자치도 내에 거주하는 청년만 신청할 수 있습니다.",
        "거주하시는 시·도의 청년 취업지원 사업을 확인해 보세요.",
    ),
    CheckItem(
        2,
        "1987. 1. 1. ~ 2008. 12. 31. 출생자만 신청할 수 있습니다(2026년 기준 18~39세).",
    ),
)

ITEM_SETS: dict[str, tuple[CheckItem, ...]] = {
    DOUBLE_SAVINGS: DOUBLE_SAVINGS_ITEMS,
    JOB_PACKAGE: JOB_PACKAGE_ITEMS,
}


def items_for(program_code: str) -> tuple[CheckItem, ...]:
    return ITEM_SETS.get(program_code, DOUBLE_SAVINGS_ITEMS)


def item_numbers(program_code: str) -> list[int]:
    """화면이 물어야 할 문항 번호. 사업이 바뀌면 문항 수가 바뀐다."""
    return [item.no for item in items_for(program_code)]


def total_items(program_code: str) -> int:
    return len(items_for(program_code))


#: 두배적금 기준 문항 수. 기존 호출부 호환용으로 남긴다.
TOTAL_ITEMS = len(DOUBLE_SAVINGS_ITEMS)


@dataclass
class SelfCheckResult:
    eligible: bool
    completed: bool
    failed_item: int | None
    reason: str
    alternative: str
    #: 이번 사업에서 물은 문항 수. 화면이 진행률을 표시하는 데 쓴다.
    total_items: int = TOTAL_ITEMS


def evaluate(
    answers: dict[str, str] | dict[int, str], program_code: str = DOUBLE_SAVINGS
) -> SelfCheckResult:
    """자가진단 답변을 평가한다.

    `answers`는 {문항번호: "예"|"아니오"}. 문항번호는 문자열/정수 모두 받는다
    (JSON 을 거치면 키가 문자열이 되기 때문).
    """
    items = items_for(program_code)
    normalized = {int(k): v for k, v in answers.items() if v}
    completed = all(item.no in normalized for item in items)

    for item in items:
        if normalized.get(item.no) == "아니오":
            return SelfCheckResult(
                eligible=False,
                completed=completed,
                failed_item=item.no,
                reason=item.reason,
                alternative=item.alternative,
                total_items=len(items),
            )

    return SelfCheckResult(
        eligible=completed,
        completed=completed,
        failed_item=None,
        reason="" if completed else "아직 답하지 않은 문항이 있습니다.",
        alternative="",
        total_items=len(items),
    )
