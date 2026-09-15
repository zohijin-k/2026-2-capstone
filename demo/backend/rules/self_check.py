"""서식2 자가진단 채점.

8문항 중 하나라도 "아니오"면 신청 자격이 없다. 부적격 사유와 대안을 함께
돌려주는 것이 핵심이다 — 콜센터 상담 3,073건 중 38%가 자격요건 문의였고,
안내가 없어서가 아니라 신청자가 스스로 확인할 방법이 없어서 반복됐다.

문항 본문은 프론트(`forms/form2-model.ts`)가 원문 그대로 들고 있다. 여기서는
판정과 사유만 다룬다.
"""

from dataclasses import dataclass

TOTAL_ITEMS = 8

#: 문항번호 → (부적격 사유, 대안 안내)
INELIGIBLE: dict[int, tuple[str, str]] = {
    1: (
        "이 사업은 공고일(2026. 3. 3.) 기준 주민등록상 주소지가 전북특별자치도인 청년만 신청할 수 있습니다.",
        "거주하시는 시·도의 청년 자산형성 지원사업을 확인해 보세요.",
    ),
    2: (
        "1986. 1. 1. ~ 2007. 12. 31. 출생자만 신청할 수 있습니다(2025. 12. 31. 기준 만 18~39세).",
        "",
    ),
    3: (
        "근로자는 2025. 10. 3. 이전부터 주 15시간 이상 계속 근로, "
        "사업자는 2025. 9. 3. 이전 개업 및 3개월(90일) 이상 운영 중이어야 합니다.",
        "",
    ),
    4: (
        "근로확인서류(4대보험 가입내역 확인서 등 5종 중 1부)를 제출하지 못하면 자격을 확인할 수 없습니다.",
        "4대사회보험 정보연계센터·고용산재보험 토탈서비스·정부24에서 발급 가능한지 먼저 확인해 보세요.",
    ),
    5: (
        "적금 계좌는 기초지자체 명의로 일괄 개설됩니다. 이 조건에 동의해야 참여할 수 있습니다.",
        "",
    ),
    6: ("제외 대상 확인에 동의해야 신청할 수 있습니다.", ""),
    7: (
        "가구 기준 중위소득 140% 이하만 신청할 수 있습니다. "
        "건강보험 자격확인서상 가구원수와 납부확인서상 고지금액('25.10~12월 평균)으로 판정합니다.",
        "",
    ),
    8: ("중도해지 사유를 확인해야 신청할 수 있습니다.", ""),
}

#: 1번 문항에서 막힌 기초생활수급자에게는 더 유리한 사업이 따로 있다.
#: 시행지침이 직접 언급하는 내용이라 안내에 포함한다.
BASIC_LIVELIHOOD_ALTERNATIVE = (
    "기초생활수급자 및 법정 차상위계층은 보건복지부 청년내일저축계좌 대상으로, "
    "해당 사업의 혜택이 더 큽니다(3년간 10만원 적립 시 1:3 정부매칭으로 약 1,440만원 수령)."
)


@dataclass
class SelfCheckResult:
    eligible: bool
    completed: bool
    failed_item: int | None
    reason: str
    alternative: str


def evaluate(answers: dict[str, str] | dict[int, str]) -> SelfCheckResult:
    """자가진단 답변을 평가한다.

    `answers`는 {문항번호: "예"|"아니오"}. 문항번호는 문자열/정수 모두 받는다
    (JSON 을 거치면 키가 문자열이 되기 때문).
    """
    normalized = {int(k): v for k, v in answers.items() if v}
    completed = all(no in normalized for no in range(1, TOTAL_ITEMS + 1))

    for no in range(1, TOTAL_ITEMS + 1):
        if normalized.get(no) == "아니오":
            reason, alternative = INELIGIBLE[no]
            if no == 6:
                alternative = BASIC_LIVELIHOOD_ALTERNATIVE
            return SelfCheckResult(
                eligible=False,
                completed=completed,
                failed_item=no,
                reason=reason,
                alternative=alternative,
            )

    return SelfCheckResult(
        eligible=completed,
        completed=completed,
        failed_item=None,
        reason="" if completed else "아직 답하지 않은 문항이 있습니다.",
        alternative="",
    )
