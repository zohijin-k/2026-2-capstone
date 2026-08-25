"""
2단계: 통합 심사 (자격 자동 점검)

Notion 회의록 "자격 미달 신청" 항목을 그대로 규칙화:
- 사업 대상이 아닌 사람이 신청
- 소득분위 기준 미충족자 신청 (예: 9분위 이하만 가능한데 10분위가 신청)
- 지원 횟수를 초과하거나 중복으로 신청
- 증빙자료의 기간이 인정되지 않는 기간인데도 신청 (-> 1단계 DOCUMENT_ISSUED_TOO_EARLY가 커버)
- 기타 잘못된 서류 등

needs_review 플래그는 향후 애매 판정 규칙(예: 서류 간 소득 정보 불일치 등)을 추가할 자리로 남겨둠.
지금은 소득분위처럼 명확한 컷오프 값은 바로 FAIL/PASS로 확정한다.
"""

from __future__ import annotations

from . import config
from .models import Applicant, Finding, ReasonCode, Status, StageResult
from .reason_messages import render


def run_stage2(applicant: Applicant) -> StageResult:
    findings: list[Finding] = []
    hard_fail = False
    needs_review = False

    # 1) 거주지 요건
    if applicant.residence_region not in config.TARGET_REGIONS:
        findings.append(Finding(ReasonCode.NOT_TARGET_REGION,
                                 render(ReasonCode.NOT_TARGET_REGION)))
        hard_fail = True

    # 2) 소득분위 기준 (예: 9분위 이하만 지원 가능 -> 10분위는 즉시 부적합)
    decile_limit = config.INCOME_DECILE_LIMIT.get(applicant.program)
    if decile_limit is not None and applicant.income_decile is not None:
        if applicant.income_decile > decile_limit:
            findings.append(Finding(
                ReasonCode.INCOME_OVER_THRESHOLD,
                render(ReasonCode.INCOME_OVER_THRESHOLD, decile=applicant.income_decile, limit=decile_limit)))
            hard_fail = True

    # 3) 지원 횟수 초과
    max_count = config.MAX_SUPPORT_COUNT.get(applicant.program)
    if max_count is not None and applicant.prior_support_count >= max_count:
        findings.append(Finding(ReasonCode.EXCEEDED_SUPPORT_COUNT,
                                 render(ReasonCode.EXCEEDED_SUPPORT_COUNT)))
        hard_fail = True

    # 4) 중복 신청
    if applicant.is_duplicate_submission:
        findings.append(Finding(ReasonCode.DUPLICATE_APPLICATION,
                                 render(ReasonCode.DUPLICATE_APPLICATION)))
        hard_fail = True

    # 5) 동시 수혜 제한 사업 충돌 (예: 청년수당 중복신청 - 콜센터 자동응답 문의 1위 항목)
    conflicts = config.CONFLICTING_BENEFIT_PROGRAMS.get(applicant.program, set())
    hit = conflicts & set(applicant.conflicting_benefits)
    if hit:
        findings.append(Finding(ReasonCode.OTHER_PROGRAM_CONFLICT,
                                 render(ReasonCode.OTHER_PROGRAM_CONFLICT, conflict=", ".join(hit))))
        hard_fail = True

    if hard_fail:
        status = Status.FAIL
    elif needs_review:
        status = Status.NEEDS_REVIEW
    else:
        status = Status.PASS
        findings.append(Finding(ReasonCode.ALL_CLEAR, render(ReasonCode.ALL_CLEAR)))

    return StageResult(stage="stage2_eligibility", status=status, findings=findings)
