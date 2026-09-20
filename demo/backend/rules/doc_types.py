"""문서 종류 문자열의 단일 소스.

데모·엔진·OCR이 같은 라벨을 써야 매칭이 된다. 문자열 불일치가 가장 흔한 연동
사고 지점이라, 여기서만 정의하고 나머지는 전부 import 해서 쓴다.

라벨은 공고문/시행지침 원문 표기를 따른다. 특히 아래 두 쌍은 이름이 한 글자
차이인데 하나만 유효하다 — 공고문이 직접 "※등본 아님", "※등록증 아님"으로
지목한 항목이다.
  - 주민등록초본 (O)  vs  주민등록등본 (X)
  - 사업자등록증명 (O) vs  사업자등록증 (X)
"""

from enum import StrEnum


class DocType(StrEnum):
    # --- 두배적금: 온라인 업로드 대상 ---
    ADMIN_INFO_CONSENT = "행정정보공동이용동의서"  # 서식5 (원문상 자필서명)

    # 근로확인서류 (㉠~㉤ 중 택1)
    INSURANCE_4 = "4대보험가입내역확인서"
    DAILY_WORK_RECORD = "고용산재보험일용근로내역서"
    LABOR_CONTRACT = "근로계약서"
    BIZ_REG_PROOF = "사업자등록증명"
    FARM_BIZ_CERT = "농업경영체증명서"
    FISHERY_BIZ_CERT = "어업경영체증명서"

    # 소득재산 증빙서류 (3종 모두)
    NHIS_PAYMENT = "건강보험료납부확인서"
    NHIS_QUALIFICATION = "건강보험자격확인서"
    NHIS_ACQUISITION_LOSS = "건강보험자격득실확인서"

    RESIDENT_ABSTRACT = "주민등록초본"

    # --- 취업지원패키지 ---
    INTERVIEW_CONFIRMATION = "면접확인서"
    PAYMENT_RECEIPT = "결제영수증"
    ID_PHOTO_COPY = "면접용사진사본"
    EXAM_CONFIRMATION = "응시확인서"
    EXAM_TRANSCRIPT = "성적표"

    # --- 필수는 아니지만 오분류 탐지를 위해 분류기가 알아야 하는 라벨 ---
    RESIDENT_CERTIFICATE = "주민등록등본"
    BIZ_REG_CERT = "사업자등록증"


#: 서로 헷갈려서 잘못 올리기 쉬운 서류 쌍.
#: 요구 서류가 아닌 쪽이 올라오면 WRONG_DOCUMENT_TYPE으로 잡는다.
CONFUSION_GROUPS: list[set[DocType]] = [
    # 공고문 미비 예시에 "초본 아닌 등본 제출"이 명시돼 있다.
    {DocType.RESIDENT_ABSTRACT, DocType.RESIDENT_CERTIFICATE},
    # 공고문 "사업자등록증명(※등록증 아님)".
    {DocType.BIZ_REG_PROOF, DocType.BIZ_REG_CERT},
    # 이름이 비슷하고 둘 다 건보공단 발급이라 자주 바뀐다.
    {DocType.NHIS_QUALIFICATION, DocType.NHIS_ACQUISITION_LOSS},
]

#: 서류를 발급받는 곳. 업로드 화면의 "발급처 바로가기" 링크에 쓴다.
ISSUER_LINKS: dict[DocType, tuple[str, str]] = {
    DocType.RESIDENT_ABSTRACT: ("정부24", "https://www.gov.kr"),
    DocType.NHIS_PAYMENT: ("국민건강보험공단", "https://www.nhis.or.kr"),
    DocType.NHIS_QUALIFICATION: ("국민건강보험공단", "https://www.nhis.or.kr"),
    DocType.NHIS_ACQUISITION_LOSS: ("국민건강보험공단", "https://www.nhis.or.kr"),
    DocType.INSURANCE_4: ("4대사회보험 정보연계센터", "https://www.4insure.or.kr"),
    DocType.DAILY_WORK_RECORD: ("고용산재보험 토탈서비스", "https://total.comwel.or.kr"),
    DocType.BIZ_REG_PROOF: ("정부24", "https://www.gov.kr"),
    DocType.FARM_BIZ_CERT: ("정부24", "https://www.gov.kr"),
    DocType.FISHERY_BIZ_CERT: ("관할 수산청", ""),
}


def confusable_with(doc_type: DocType) -> set[DocType]:
    """`doc_type` 자리에 잘못 올라올 수 있는 서류들."""
    for group in CONFUSION_GROUPS:
        if doc_type in group:
            return group - {doc_type}
    return set()
