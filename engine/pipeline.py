"""
통합 파이프라인: OCR 결과 -> 1단계 -> 2단계 -> 최종 판정

+ '질문 1'에 대한 구체적 답 (Notion 회의록 요청사항):
  "부적합 판단을 받아 판정 요청을 보낼 서류는 어떤 정보를 담아야하나요?"
  -> build_review_payload()가 그 답. 담당자 화면/카톡 알림에 그대로 넘길 수 있는 구조.
"""

from __future__ import annotations
from datetime import datetime

from .models import Applicant, Document, FinalResult, Status
from .stage1_document_check import run_stage1
from .stage2_eligibility_check import run_stage2


def _combine_status(s1: Status, s2: Status | None) -> Status:
    statuses = [s1] + ([s2] if s2 else [])
    if Status.FAIL in statuses:
        return Status.FAIL
    if Status.NEEDS_REVIEW in statuses:
        return Status.NEEDS_REVIEW
    return Status.PASS


def build_review_payload(applicant: Applicant, documents: list[Document], final: FinalResult) -> dict:
    """담당자에게 넘어가는 심사 요청 패키지.

    포함 항목 (질문1 답변):
    - applicant_id: 신청 시 부여된 고유번호 (필수 — 이게 없으면 담당자가 원본 서류와 매칭 불가)
    - program / name / birth_date: 신청자 식별 최소 정보
    - documents: 각 서류의 파일명(추정) + doc_type + OCR신뢰도 + 원본 PDF 다운로드 참조용 doc_type 키
      (실제 파일 자체는 PDF 그대로 전송 가능해야 함 -> 원본 파일 URL/경로는 데모사이트 쪽에서 채워 넣을 필드로 남김)
    - reasons: 사유코드 + 신청자향 메시지 (담당자도 같은 문구를 보면 됨 -> 이중 커뮤니케이션 방지)
    - stage: 어느 단계에서 걸렸는지 (서류 자체 문제 vs 자격 요건 문제 구분)
    - recommended_action: FAIL이면 "반려/보완요청", NEEDS_REVIEW면 "육안 확인 필요"
    """
    reasons = []
    for stage_result in [final.stage1, final.stage2]:
        if stage_result is None:
            continue
        for f in stage_result.findings:
            if f.code.value == "ALL_CLEAR":
                continue
            reasons.append({
                "stage": stage_result.stage,
                "code": f.code.value,
                "message": f.message,
                "doc_type": f.doc_type,
            })

    return {
        "applicant_id": applicant.applicant_id,   # 고유번호 (필수)
        "name": applicant.name,
        "program": applicant.program,
        "submitted_at": datetime.now().isoformat(timespec="seconds"),
        "final_status": final.status.value,
        "documents": [
            {
                "doc_type": d.doc_type,
                "file_format": d.file_format,
                "ocr_confidence": round(d.ocr_confidence, 3),
                # TODO(지빈): 실제 원본 PDF/이미지 경로 또는 다운로드 URL을 여기에 채워야
                # 담당자가 "AI 점검 결과와 원본 서류를 함께" 볼 수 있음 (Notion 플로우 8번)
                "file_ref": None,
            }
            for d in documents
        ],
        "reasons": reasons,
        "recommended_action": (
            "반려/보완요청 안내" if final.status == Status.FAIL
            else "담당자 육안 확인 필요" if final.status == Status.NEEDS_REVIEW
            else "자동 승인"
        ),
    }


def run_pipeline(applicant: Applicant, documents: list[Document]) -> FinalResult:
    stage1 = run_stage1(applicant, documents)

    # 서류 자체가 확정 FAIL이면 2단계(자격 심사)까지 굳이 안 돌려도 되지만,
    # "부적합 사유를 한 번에 다 안내"하는 게 재문의를 줄인다는 콜센터 데이터 근거(반복문의 다수)에 따라
    # 항상 2단계까지 돌리고 사유를 합쳐서 보여준다.
    stage2 = run_stage2(applicant)

    final_status = _combine_status(stage1.status, stage2.status)

    final = FinalResult(
        applicant_id=applicant.applicant_id,
        status=final_status,
        stage1=stage1,
        stage2=stage2,
    )

    if final_status in (Status.FAIL, Status.NEEDS_REVIEW):
        final.review_payload = build_review_payload(applicant, documents, final)

    return final
