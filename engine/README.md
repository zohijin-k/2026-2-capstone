서류 심사 엔진 (engine/)
전북청년 함께 두배적금 서류 자동심사 시스템의 판단 로직 모듈. OCR로 판독된 서류 데이터와 신청자 정보를 입력받아 적합(PASS) / 부적합(FAIL) / 담당자 확인 필요(NEEDS_REVIEW) 3단계로 판정하고, 부적합/애매 판정 시 담당자에게 넘길 심사 요청 패키지까지 만들어준다.

OCR 자체(이미지→텍스트 판독)와 화면 UI는 이 모듈의 범위가 아니다. 데모 사이트(지빈)가 OCR 결과를 아래 스키마에 맞게 넘겨주면, 이 엔진은 그 값을 가지고 판정만 한다.
판단 흐름
신청자 정보 + 서류별 OCR 결과

        │

        ▼

[1단계] 서류 적합성 검사 (stage1_document_check.py)

  - 필수서류 제출 여부

  - 서류 종류 오분류 (등본 자리에 초본 등)

  - 서명 여부

  - 이미지 화질

  - 발급일이 인정 기준일 이후인지

  - 업로드 시 사용자가 직접 입력한 발급일과 OCR 판독 발급일 일치 여부

  - OCR 판독 신뢰도

        │

        ▼

[2단계] 통합 자격 심사 (stage2_eligibility_check.py)

  - 거주지 요건

  - 소득분위 기준

  - 지원 횟수 초과 / 중복 신청

  - 동시 수혜 제한 사업 충돌 (예: 청년수당)

        │

        ▼

run_pipeline() 이 두 단계 결과를 합쳐 최종 판정 (pipeline.py)

  - FAIL 또는 NEEDS_REVIEW면 담당자 심사 요청 패키지(review_payload) 자동 생성

두 단계 모두 하드 FAIL이 하나라도 있으면 최종 FAIL, 아니면 NEEDS_REVIEW가 하나라도 있으면 NEEDS_REVIEW, 전부 통과면 PASS. 서류에 문제가 있어도 자격 심사까지 항상 끝까지 돌려서 사유를 한 번에 다 모아 보여준다 (신청자가 하나씩 고치고 재문의하는 반복을 줄이기 위함 — 콜센터 반복 문의 데이터가 근거).
파일 구성
파일
역할
models.py
데이터 스키마 (Applicant, Document, RequiredDocumentSpec, Finding, StageResult, FinalResult) 및 사유 코드(ReasonCode) 정의
config.py
심사 기준값. 팀에서 임의로 정한 값이므로 TF 확정값이 오면 여기만 수정하면 됨
reason_messages.py
사유 코드 → 신청자에게 보여줄 안내 문구 매핑
stage1_document_check.py
1단계 로직
stage2_eligibility_check.py
2단계 로직
pipeline.py
1·2단계를 통합 실행하고 최종 판정 + 담당자 심사 요청 패키지 생성

사용법 (데모 사이트 연동)
from datetime import date

from engine.models import Applicant, Document

from engine.pipeline import run_pipeline

applicant = Applicant(

    applicant_id="APP-2027-000123",   # 신청 시 부여되는 고유번호 — 필수

    name="홍길동",

    birth_date=date(1998, 5, 1),

    residence_region="전주시",

    program="전북청년적금",

    income_decile=5,                  # 건강보험료 기준 소득분위 (1~10)

    prior_support_count=0,

    is_duplicate_submission=False,

    conflicting_benefits=[],

)

documents = [

    Document(

        doc_type="주민등록등본",        # OCR 분류기가 반환하는 라벨과 반드시 일치해야 함

        file_format="pdf",

        ocr_confidence=0.95,           # OCR 엔진이 반환하는 필드 단위 평균 신뢰도

        image_quality_score=0.9,

        has_signature=True,

        issue_date=date(2026, 8, 10),         # OCR이 서류 본문에서 읽은 발급일

        declared_issue_date=date(2026, 8, 10), # 업로드 화면 옆칸에 사용자가 직접 입력한 발급일

    ),

    # ... 나머지 필수서류

]

result = run_pipeline(applicant, documents)

result.status            # Status.PASS / FAIL / NEEDS_REVIEW

result.stage1.findings   # 1단계 상세 사유 리스트

result.stage2.findings   # 2단계 상세 사유 리스트

result.review_payload    # FAIL/NEEDS_REVIEW일 때만 존재, 담당자 화면에 그대로 전달

python demo_run.py (루트에서 실행)를 돌리면 8개 시나리오(완전적합 / 발급일 기준일 이전 / 입력값-OCR값 불일치 / 등본-초본 오분류 / 서명누락 / 소득분위 초과 / 지원횟수초과 / OCR저신뢰)가 콘솔에 순서대로 출력된다.
config.py에서 반드시 확인해야 할 값
OCR_CONFIDENCE_THRESHOLD   # 이 값 미만이면 NEEDS_REVIEW (현재 0.85, 가정값)

IMAGE_QUALITY_THRESHOLD    # 화질 불량 판정 기준 (현재 0.6, 가정값)

DOCUMENT_ISSUE_CUTOFF      # 서류 발급일 인정 기준일 (사업별, 현재 2026-08-01, 가정값)

INCOME_DECILE_LIMIT        # 소득분위 컷오프 (현재 9분위 이하 통과, 가정값)

MAX_SUPPORT_COUNT          # 지원 가능 횟수 (사업별)

TARGET_REGIONS             # 지원 대상 시/군 목록

REQUIRED_DOCUMENTS         # 사업별 필수서류 목록 + 서명 필요 여부 + 발급일 대조 여부

DOCUMENT_TYPE_CONFUSION_GROUPS  # 등본/초본처럼 헷갈리기 쉬운 서류 쌍
데모사이트(지빈) 쪽과 맞춰야 할 것
doc_type 네이밍: config.REQUIRED_DOCUMENTS에 쓴 문자열("주민등록등본" 등)과 OCR 분류 결과 라벨이 정확히 일치해야 매칭됨
declared_issue_date 입력 UI: 서류 업로드 칸 옆에 발급일 직접 입력 필드가 있어야 DECLARED_DATE_MISMATCH 체크가 동작함
review_payload.documents[].file_ref: 현재 null로 비워둠. 담당자가 "AI 점검 결과와 원본 서류를 함께" 볼 수 있어야 하므로, 원본 PDF 다운로드 경로/URL을 이 필드에 채워 넣어야 함
아직 가짜값인 것 (9/15 전 TF 확정 필요)
config.py 상단에 전부 주석으로 표시해뒀다. 배점표, 실제 중위소득/소득분위 기준, 서류별 발급일 인정 기준일, OCR 신뢰도 컷라인은 모두 회의 전까지 팀이 임의로 정한 값이다.
TODO (다음 단계)
실제 OCR 결과(업스테이지/네이버 클로바 등) → Document 스키마로 매핑하는 어댑터 작성
review_payload에 원본 파일 참조(file_ref) 채우기 — 데모사이트 저장소 구조 확정 후
TF 확정 배점표/자격기준을 config.py에 반영
애매 판정(NEEDS_REVIEW) 케이스 확장 — 현재는 OCR 신뢰도만 애매 판정, 추후 서류 간 정보 불일치 등 추가 가능

