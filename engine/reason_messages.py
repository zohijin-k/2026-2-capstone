"""
사유 코드 -> 신청자 안내 문구 매핑.

Notion 회의록 예시 톤 그대로 따름:
"제출한 서류에 서명이 없습니다" / "주민등록 초본이 제출되지 않았습니다."
-> 담당자가 아니라 '시스템이' 이 톤으로 말해도 어색하지 않게, 구체적이고 사무적으로.
"""

from .models import ReasonCode

MESSAGES: dict[ReasonCode, str] = {
    ReasonCode.MISSING_REQUIRED_DOC: "필수 제출 서류 중 '{doc_type}'가 제출되지 않았습니다.",
    ReasonCode.WRONG_DOCUMENT_TYPE: "'{doc_type}'가 필요한 자리에 다른 종류의 서류가 제출되었습니다. 서류 종류를 다시 확인해 주세요.",
    ReasonCode.MISSING_SIGNATURE: "제출한 '{doc_type}'에 서명이 없습니다. 서명 후 다시 제출해 주세요.",
    ReasonCode.LOW_IMAGE_QUALITY: "'{doc_type}' 이미지의 화질이 낮아 내용을 확인하기 어렵습니다. 선명한 사진으로 다시 제출해 주세요.",
    ReasonCode.LOW_OCR_CONFIDENCE: "'{doc_type}'의 일부 항목이 자동으로 판독되지 않았습니다. 담당자가 직접 확인할 예정입니다.",
    ReasonCode.DOCUMENT_ISSUED_TOO_EARLY: "'{doc_type}'의 발급일({issue_date})이 인정 기준일({cutoff}) 이전입니다. {cutoff} 이후 발급본으로 다시 제출해 주세요.",
    ReasonCode.DECLARED_DATE_MISMATCH: "입력하신 '{doc_type}' 발급일({declared})과 서류에서 확인된 발급일({actual})이 일치하지 않습니다.",
    ReasonCode.UNREADABLE_FILE: "'{doc_type}' 파일을 열 수 없습니다. 비밀번호가 걸려있지 않은 파일로 다시 제출해 주세요.",
    ReasonCode.NOT_TARGET_REGION: "신청 자격 요건 중 거주지 요건을 충족하지 않습니다.",
    ReasonCode.NOT_TARGET_AGE: "신청 자격 요건 중 연령 요건을 충족하지 않습니다.",
    ReasonCode.INCOME_OVER_THRESHOLD: "소득분위({decile}분위)가 지원 가능 기준({limit}분위 이하)을 초과했습니다.",
    ReasonCode.DUPLICATE_APPLICATION: "동일 사업에 중복으로 신청되어 있습니다.",
    ReasonCode.EXCEEDED_SUPPORT_COUNT: "해당 사업의 지원 가능 횟수를 초과했습니다.",
    ReasonCode.OTHER_PROGRAM_CONFLICT: "동시 수혜가 제한된 다른 사업({conflict})에 참여 중입니다.",
    ReasonCode.ALL_CLEAR: "제출하신 내용에 특이사항이 없습니다.",
}


def render(code: ReasonCode, **kwargs) -> str:
    template = MESSAGES[code]
    try:
        return template.format(**kwargs)
    except KeyError:
        return template
