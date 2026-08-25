"""
심사 기준 설정값 — 회의 전 데모용으로 우리가 임의로 정한 값.

TF팀 미팅에서 실제 배점표/공고문이 확정되면 이 파일의 값만 바꾸면 된다.
로직 코드(stage1/stage2)는 건드릴 필요 없음.
"""

from datetime import date

from .models import RequiredDocumentSpec

# --- 1단계 판단 임계값 ---
OCR_CONFIDENCE_THRESHOLD = 0.85
IMAGE_QUALITY_THRESHOLD = 0.6

# 서류 발급일 인정 기준일 (이 날짜 '이후' 발급분만 인정)
# 데모 시나리오: "2026년 8월 이후 발행된 등본만 인정, 7월 등본이면 즉시 부적합"
DOCUMENT_ISSUE_CUTOFF = {
    "전북청년적금": date(2026, 8, 1),
    "취업지원패키지": date(2026, 8, 1),
}

# --- 2단계 판단 임계값 ---
# 소득분위 기준 (이 값 '이하'만 통과. 예: 9분위 이하만 지원 가능 -> 10분위는 부적합)
INCOME_DECILE_LIMIT = {
    "전북청년적금": 9,
    "취업지원패키지": 9,
}

MAX_SUPPORT_COUNT = {
    "전북청년적금": 1,          # 동일 사업 재수혜 불가 (연차별 정책 바뀌면 여기만 수정)
    "취업지원패키지": 2,
}

TARGET_REGIONS = {
    "전주시", "군산시", "익산시", "정읍시", "남원시", "김제시", "완주군",
    "진안군", "무주군", "장수군", "임실군", "순창군", "고창군", "부안군",
}

# 청년적금과 동시 수혜 불가한 사업 목록 (콜센터 문의 "청년수당 중복신청" 대응)
CONFLICTING_BENEFIT_PROGRAMS = {
    "전북청년적금": {"청년수당"},
    "취업지원패키지": set(),
}

# --- 사업별 필수 서류 스펙 ---
# doc_type 문자열은 OCR 분류기가 반환하는 라벨과 반드시 일치시킬 것 (지빈 쪽과 네이밍 합의 필요)
# min_issue_date는 실행 시점에 DOCUMENT_ISSUE_CUTOFF에서 채워 넣는다 (아래 _build 참고).
REQUIRED_DOCUMENTS: dict[str, list[RequiredDocumentSpec]] = {
    "전북청년적금": [
        RequiredDocumentSpec(doc_type="주민등록등본", required=True, requires_signature=False, check_declared_date=True),
        RequiredDocumentSpec(doc_type="소득금액증명원", required=True, requires_signature=False, check_declared_date=True),
        RequiredDocumentSpec(doc_type="건강보험료납부확인서", required=True, requires_signature=False, check_declared_date=True),
        RequiredDocumentSpec(doc_type="행정정보공동이용동의서", required=True, requires_signature=True),
    ],
    "취업지원패키지": [
        RequiredDocumentSpec(doc_type="주민등록등본", required=True, requires_signature=False, check_declared_date=True),
        RequiredDocumentSpec(doc_type="졸업(예정)증명서", required=True, requires_signature=False),
        RequiredDocumentSpec(doc_type="참여동의서", required=True, requires_signature=True),
    ],
}

# 프로그램별 cutoff 날짜를 각 서류 스펙에 실제로 주입 (모듈 로드 시 1회 실행)
for _program, _specs in REQUIRED_DOCUMENTS.items():
    _cutoff = DOCUMENT_ISSUE_CUTOFF.get(_program)
    for _spec in _specs:
        if _cutoff is not None:
            _spec.min_issue_date = _cutoff

# "등본인데 초본을 올린다" 같은 오분류를 잡기 위한 유사 서류군 매핑
# OCR 분류 결과가 이 그룹 중 required와 다른 항목으로 나오면 WRONG_DOCUMENT_TYPE
DOCUMENT_TYPE_CONFUSION_GROUPS = [
    {"주민등록등본", "주민등록초본"},
    {"소득금액증명원", "지방세납세증명서"},
]
