"""
서류 심사 엔진 - 데이터 모델

OCR 판독 결과 및 신청자 정보를 담는 표준 스키마.
지빈(데모사이트)이 이 스키마로 데이터를 넘겨주면 엔진이 그대로 판단한다.
채운(대시보드)도 이 결과 객체(StageResult)를 그대로 집계에 쓸 수 있다.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional


class Status(str, Enum):
    PASS = "PASS"                # 적합
    FAIL = "FAIL"                # 부적합 (확정)
    NEEDS_REVIEW = "NEEDS_REVIEW"  # 애매함 -> 담당자 확인 필요


class ReasonCode(str, Enum):
    # --- 1단계: 서류 적정성 ---
    MISSING_REQUIRED_DOC = "MISSING_REQUIRED_DOC"
    WRONG_DOCUMENT_TYPE = "WRONG_DOCUMENT_TYPE"          # 등본 요구했는데 초본 제출 등
    MISSING_SIGNATURE = "MISSING_SIGNATURE"
    LOW_IMAGE_QUALITY = "LOW_IMAGE_QUALITY"              # 화질 문제로 판독 불가
    LOW_OCR_CONFIDENCE = "LOW_OCR_CONFIDENCE"            # OCR 신뢰도 낮음 -> 검토 필요
    DOCUMENT_ISSUED_TOO_EARLY = "DOCUMENT_ISSUED_TOO_EARLY"  # 발급일이 인정 기준일(컷오프) 이전
    DECLARED_DATE_MISMATCH = "DECLARED_DATE_MISMATCH"    # 사용자가 직접 입력한 발급일 != 서류상 발급일
    UNREADABLE_FILE = "UNREADABLE_FILE"                  # 파일 자체가 손상/암호화 등

    # --- 2단계: 자격 요건 ---
    NOT_TARGET_REGION = "NOT_TARGET_REGION"              # 전북 거주 요건 미충족
    NOT_TARGET_AGE = "NOT_TARGET_AGE"                    # 연령 요건 미충족
    INCOME_OVER_THRESHOLD = "INCOME_OVER_THRESHOLD"      # 소득분위 기준 초과
    DUPLICATE_APPLICATION = "DUPLICATE_APPLICATION"      # 동일 사업 중복 신청
    EXCEEDED_SUPPORT_COUNT = "EXCEEDED_SUPPORT_COUNT"    # 지원 횟수 초과
    OTHER_PROGRAM_CONFLICT = "OTHER_PROGRAM_CONFLICT"    # 청년수당 등 중복수혜 제한 위반

    # --- 통과 ---
    ALL_CLEAR = "ALL_CLEAR"


@dataclass
class Document:
    """OCR 판독이 끝난 서류 한 건. doc_type은 지빈 쪽에서 업로드 시 지정하거나
    OCR 분류 모델이 판별한 값(예: '주민등록등본', '주민등록초본', '소득금액증명원').

    issue_date vs declared_issue_date:
    - issue_date: OCR이 서류 본문에서 직접 읽어낸 '진짜' 발급일
    - declared_issue_date: 업로드 화면에서 사용자가 옆 칸에 직접 입력한 발급일
      (지빈 쪽 UI: "등본 업로드 후 옆 칸에 등본 발행일을 작성" 요구사항 대응)
      두 값을 대조해서 다르면 즉시 부적합 처리 -> 위변조/오업로드 방지 + OCR 오독 방지 이중 장치
    """
    doc_type: str
    file_format: str                       # "pdf" | "jpg" | "png" ...
    ocr_confidence: float                  # 0.0 ~ 1.0, OCR 판독 엔진이 반환하는 필드 단위 평균 신뢰도
    image_quality_score: float             # 0.0 ~ 1.0, 화질/선명도 점수 (블러/저해상도 감지용)
    has_signature: Optional[bool]          # 서명란 감지 결과. 서명 불필요 서류는 None
    issue_date: Optional[date]             # 서류 발급일 (OCR 추출, 판단의 기준값)
    declared_issue_date: Optional[date] = None  # 사용자가 업로드 시 직접 입력한 발급일
    extracted_fields: dict = field(default_factory=dict)  # {"성명": "...", "생년월일": "...", ...}
    is_encrypted_or_corrupted: bool = False


@dataclass
class RequiredDocumentSpec:
    """사업별로 어떤 서류가 필수인지 정의. config.py에서 실제 값 주입."""
    doc_type: str
    required: bool = True
    requires_signature: bool = False
    min_issue_date: Optional[date] = None   # 이 날짜 '이후' 발급분만 인정 (예: 공고일/모집 시작일)
    check_declared_date: bool = False       # True면 사용자 직접입력 발급일과 OCR값 대조


@dataclass
class Applicant:
    """신청자 정보. 대부분 신청 폼 입력값 + OCR로 보완된 값."""
    applicant_id: str
    name: str
    birth_date: date
    residence_region: str                  # 시/군 (예: "전주시")
    program: str                           # "전북청년적금" | "취업지원패키지"
    income_decile: Optional[int]           # 건강보험료 기준 소득분위 (1~10, 10이 가장 높음)
    prior_support_count: int = 0           # 동일/유사 사업 과거 수혜 횟수
    is_duplicate_submission: bool = False  # 동일 회차 중복 접수 여부 (시스템에서 사전 감지)
    conflicting_benefits: list[str] = field(default_factory=list)  # 청년수당 등 중복불가 항목 보유 여부


@dataclass
class Finding:
    code: ReasonCode
    message: str                 # 신청자에게 보여줄 안내 문구 (구체적 사유)
    doc_type: Optional[str] = None


@dataclass
class StageResult:
    stage: str                   # "stage1_document" | "stage2_eligibility"
    status: Status
    findings: list[Finding] = field(default_factory=list)


@dataclass
class FinalResult:
    applicant_id: str
    status: Status
    stage1: StageResult
    stage2: Optional[StageResult]
    review_payload: Optional[dict] = None  # 부적합/애매 시 담당자 심사 요청에 첨부할 정보 (질문 1 관련)
