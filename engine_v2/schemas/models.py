"""엔진 입력·출력 계약.

모든 서류 판독 부품(초본, 면접확인서, 영수증 ...)은 DocumentResult 형태로 결과를 낸다.
데모 사이트 / 대시보드는 이 모델만 보고 붙는다.

원칙
- 엔진은 신청자 입력값(ApplicantInput, declared_values)을 믿지 않는다. 검증 대상일 뿐이다.
- 배점 등 대외비 값은 ApplicationResult.internal 에만 둔다.
  신청자에게 보낼 때는 반드시 to_applicant_view() 를 거친다.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 공통 열거형
# ---------------------------------------------------------------------------

class ProgramId(str, Enum):
    DOUBLING_SAVINGS = "doubling_savings"  # 전북청년 함께 두배적금
    JOB_PACKAGE = "job_package"            # 청년 취업지원 패키지


class DocType(str, Enum):
    RESIDENT_ABSTRACT = "resident_abstract"      # 주민등록표 초본
    RESIDENT_REGISTER = "resident_register"      # 주민등록표 등본
    NHIS_PAYMENT = "nhis_payment"                  # 건강보험료 납부확인서
    NHIS_QUALIFICATION = "nhis_qualification"     # 건강보험 자격확인 통보서
    NHIS_ACQUISITION_LOSS = "nhis_acquisition_loss"  # 건강보험 자격득실확인서
    INSURANCE_4 = "insurance_4"                    # 4대 사회보험 가입내역 확인서
    HEALTH_INSURANCE = "health_insurance"        # 건강보험 자격득실확인서
    INTERVIEW_CONFIRM = "interview_confirm"      # 면접확인서
    RECEIPT = "receipt"                          # 결제영수증 (정장대여·사진관·자격증)
    EXAM_ADMISSION = "exam_admission"            # 자격증 응시확인서
    EXAM_SCORE = "exam_score"                    # 성적표
    BANKBOOK = "bankbook"                        # 통장사본
    CONSENT_FORM = "consent_form"                # 개인정보·행정정보공동이용 동의서
    UNKNOWN = "unknown"


class FieldSource(str, Enum):
    TEXT_LAYER = "text_layer"  # 전자발급 PDF 텍스트 직접 추출 (가장 신뢰)
    OCR = "ocr"                # 스캔·사진 OCR
    VLM = "vlm"                # 로컬 비전언어모델 (비정형 서류)


class CheckStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"  # 필드 누락·저신뢰 등으로 판단 불가


class Verdict(str, Enum):
    SUITABLE = "적합"
    UNSUITABLE = "부적합"
    NEEDS_REVIEW = "검토필요"


# ---------------------------------------------------------------------------
# 입력
# ---------------------------------------------------------------------------

class ApplicantInput(BaseModel):
    """신청자가 폼에 입력한 값. 엔진은 이것을 서류로 검증한다."""
    name: str
    birth_date: date
    phone: Optional[str] = None
    address: Optional[str] = None
    extra: dict[str, Any] = Field(default_factory=dict, description="사업별 추가 입력값 (근로유형 등)")


class DocumentInput(BaseModel):
    doc_id: str
    declared_type: DocType = Field(description="신청자가 업로드한 칸의 서류 종류")
    file_path: str
    declared_values: dict[str, Any] = Field(
        default_factory=dict,
        description="서류별 신청자 입력값. 예: {'issue_date': '2026-03-02'}",
    )


class ApplicationInput(BaseModel):
    application_id: str
    program_id: ProgramId
    announcement_date: date = Field(description="공고일. 나이·발급일·거주기간 계산 기준일")
    applicant: ApplicantInput
    documents: list[DocumentInput]
    application_date: date | None = None
    criteria: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# 서류 단위 출력
# ---------------------------------------------------------------------------

class BBox(BaseModel):
    """원본 서류 위 근거 위치. 좌표 단위는 PDF point (좌상단 원점)."""
    page: int = Field(ge=0)
    x0: float
    y0: float
    x1: float
    y1: float


class ExtractedField(BaseModel):
    value: Any = Field(description="정규화된 값. 날짜는 date, 금액은 int")
    raw_text: str = Field(description="서류에 적힌 원문 그대로")
    confidence: float = Field(ge=0.0, le=1.0)
    source: FieldSource
    bbox: Optional[BBox] = None


class Evidence(BaseModel):
    field: str                         # 예: "issue_date" 또는 "applicant.birth_date"
    value: Any
    bbox: Optional[BBox] = None


class CheckResult(BaseModel):
    rule_id: str                       # 규칙팩 안의 규칙 ID. 예: "abstract.issue_date_recent"
    rule_type: str                     # 규칙 유형. 예: "date_within", "equals_input"
    status: CheckStatus
    applicant_message: str = Field(description="신청자용. 기준 파라미터·배점 노출 금지")
    reviewer_message: str = Field(description="담당자용 상세 설명")
    evidence: list[Evidence] = Field(default_factory=list)


class DocumentResult(BaseModel):
    doc_id: str
    declared_type: DocType
    detected_type: DocType
    type_confidence: float = Field(ge=0.0, le=1.0)
    fields: dict[str, ExtractedField] = Field(default_factory=dict)
    checks: list[CheckResult] = Field(default_factory=list)
    verdict: Verdict
    review_reasons: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 신청 단위 출력
# ---------------------------------------------------------------------------

class InternalAssessment(BaseModel):
    """담당자 전용. 배점은 존재 자체가 대외비이므로 신청자 출력에 절대 포함하지 않는다."""
    scores: dict[str, float] = Field(default_factory=dict)   # 예: {"age": 10, "residence": 20}
    total_score: Optional[float] = None
    notes: list[str] = Field(default_factory=list)


class ApplicationResult(BaseModel):
    application_id: str
    program_id: ProgramId
    documents: list[DocumentResult]
    missing_doc_types: list[DocType] = Field(default_factory=list)
    status: Verdict
    internal: InternalAssessment = Field(default_factory=InternalAssessment)

    def to_applicant_view(self) -> "ApplicantView":
        return ApplicantView(
            application_id=self.application_id,
            status=self.status,
            missing_doc_types=self.missing_doc_types,
            documents=[
                ApplicantDocumentView(
                    doc_id=d.doc_id,
                    declared_type=d.declared_type,
                    verdict=d.verdict,
                    messages=list(dict.fromkeys(  # 같은 안내 문구는 한 번만
                        c.applicant_message for c in d.checks
                        if c.status != CheckStatus.PASS and c.applicant_message)),
                )
                for d in self.documents
            ],
        )


# ---------------------------------------------------------------------------
# 신청자용 출력 (화이트리스트 방식: 여기 정의된 필드만 나간다)
# ---------------------------------------------------------------------------

class ApplicantDocumentView(BaseModel):
    doc_id: str
    declared_type: DocType
    verdict: Verdict
    messages: list[str] = Field(description="보완 안내 문구만")


class ApplicantView(BaseModel):
    application_id: str
    status: Verdict
    missing_doc_types: list[DocType]
    documents: list[ApplicantDocumentView]
