# 기술 설계 — 데모 사이트

`prd.md`의 R1~R7을 어떻게 구현할지에 대한 설계다. 결정 사항과 근거만 적고, 실행 순서는 `implement.md`에 둔다.

---

## 1. 시스템 경계

```
┌─────────────────────────────────────────────────────────────┐
│  브라우저                                                     │
│  ┌──────────────────────┐   ┌──────────────────────────┐    │
│  │ 신청자 SPA            │   │ 담당자 SPA                │    │
│  │ 자가진단·신청서·동의   │   │ 접수목록·분할심사뷰       │    │
│  │ 업로드·마이페이지      │   │ (pdf.js 인라인 렌더)      │    │
│  └──────────┬───────────┘   └────────────┬─────────────┘    │
└─────────────┼────────────────────────────┼──────────────────┘
              │  REST (JSON)               │  REST + inline stream
┌─────────────▼────────────────────────────▼──────────────────┐
│  FastAPI (demo/backend)                                      │
│  ┌────────────┐ ┌──────────────┐ ┌────────────────────────┐ │
│  │ api/       │ │ ocr/         │ │ rules/                 │ │
│  │ 신청·업로드 │ │ OcrAdapter   │ │ scoring.py (심사표100) │ │
│  │ 심사·파일   │ │ 3-tier       │ │ required_docs.py       │ │
│  └─────┬──────┘ └──────┬───────┘ │ subsidy.py (실비계산)  │ │
│        │               │         └───────────┬────────────┘ │
│        │               │                     │              │
│  ┌─────▼───────────────▼─────────────────────▼────────────┐ │
│  │ engine_adapter.py  ← 유일한 엔진 접점                   │ │
│  └─────────────────────────┬──────────────────────────────┘ │
└────────────────────────────┼────────────────────────────────┘
                             │ import
                    ┌────────▼────────┐
                    │ engine/ (진)     │  run_pipeline()
                    └─────────────────┘
        ┌──────────────┐        ┌──────────────┐
        │ SQLite       │        │ storage/     │  업로드 원본
        └──────────────┘        └──────────────┘
```

**경계 원칙**
- `engine/`은 이 태스크에서 **수정하지 않는다.** 모든 호출은 `engine_adapter.py`를 통한다. 엔진 스키마가 바뀌어도 어댑터 한 파일만 고친다 (C2 대응).
- `dashboard/`(채운)와는 코드를 공유하지 않는다. 필요하면 나중에 `demo/backend`의 `/api/officer/applications`를 집계 소스로 노출한다 (C4).

---

## 2. 스택 선택

| 영역 | 선택 | 근거 |
|---|---|---|
| 백엔드 | FastAPI (Python 3.12+) | 엔진이 Python. `run_pipeline()`을 프로세스 내 import로 직접 호출 — 데모에서 HTTP 홉을 하나 줄인다 |
| DB | SQLite + SQLModel | 파일 하나로 배포/리셋. 시연 전 `reset.py`로 초기화 |
| 프론트 | React 18 + Vite + TypeScript | 다단계 폼·즉시 피드백·분할 뷰어 등 클라이언트 상태가 많다. `dashboard/`도 같은 스택이라 팀 내 일관성 유지 |
| 스타일 | Tailwind CSS | 공공 서비스풍 UI를 빠르게 조립 |
| PDF 렌더 | pdf.js | R4.1의 "다운로드 없이 브라우저 인라인"을 만족하는 사실상 유일한 선택. bbox 하이라이트 오버레이도 여기에 얹는다 |
| 전자서명 | `signature_pad` | 캔버스 서명 (R1.2) |
| PDF 텍스트 추출 | PyMuPDF (`fitz`) | 정부24·건보공단 발급 PDF는 텍스트 레이어 보유. `pypdf`보다 좌표(bbox) 추출이 쉬워 R2.4에 유리 |
| 파일 저장 | 로컬 `demo/storage/` | 데모 범위. 저장소 커밋 금지 (R7.2) |

---

## 3. 도메인 모델

### 3.1 프로그램 설정 (`rules/programs.py`)

사업별 상수를 **한 곳에** 모은다. 두배적금/취업패키지 분기(R6)가 코드 전체에 흩어지지 않게 하기 위함이다.

```python
@dataclass(frozen=True)
class ProgramConfig:
    code: str                      # "double_savings" | "job_package"
    name: str
    announcement_date: date        # 두배적금 2026-03-03
    document_cutoff: date          # 두배적금 2026-03-03 / 취업패키지 2026-01-01
    age_basis_date: date           # 두배적금 2025-12-31 / 취업패키지 2026-01-01
    birth_range: tuple[date, date]
    selection: Literal["scored", "first_come"]
    supplement_days: int | None    # 두배적금 None(보완불가) / 취업패키지 7
    quota_by_region: dict[str, int] | None
    has_income_requirement: bool
```

### 3.2 문서 타입 상수 (`rules/doc_types.py`)

문자열 불일치가 가장 흔한 연동 사고 지점이다. 데모·엔진·OCR이 **같은 상수 모듈**을 참조한다.

```python
class DocType(StrEnum):
    RESIDENT_ABSTRACT        = "주민등록초본"        # ※ 등본 아님
    RESIDENT_CERTIFICATE     = "주민등록등본"        # 오분류 탐지용 (필수 아님)
    NHIS_PAYMENT             = "건강보험료납부확인서"
    NHIS_QUALIFICATION       = "건강보험자격확인서"
    NHIS_ACQUISITION_LOSS    = "건강보험자격득실확인서"
    INSURANCE_4              = "4대보험가입내역확인서"
    DAILY_WORK_RECORD        = "고용산재보험일용근로내역서"
    LABOR_CONTRACT           = "근로계약서"
    BIZ_REG_PROOF            = "사업자등록증명"      # ※ 등록증 아님
    BIZ_REG_CERT             = "사업자등록증"        # 오분류 탐지용
    FARM_BIZ_CERT            = "농업경영체증명서"
    FISHERY_BIZ_CERT         = "어업경영체증명서"
    ADMIN_INFO_CONSENT       = "행정정보공동이용동의서"
    # 취업지원패키지
    INTERVIEW_CONFIRMATION   = "면접확인서"
    PAYMENT_RECEIPT          = "결제영수증"
    ID_PHOTO_COPY            = "면접용사진사본"
    EXAM_CONFIRMATION        = "응시확인서"
    EXAM_TRANSCRIPT          = "성적표"

CONFUSION_PAIRS = [
    {DocType.RESIDENT_ABSTRACT, DocType.RESIDENT_CERTIFICATE},   # 공고문이 직접 지목한 미비 사유
    {DocType.BIZ_REG_PROOF, DocType.BIZ_REG_CERT},
    {DocType.NHIS_QUALIFICATION, DocType.NHIS_ACQUISITION_LOSS},
]
```

### 3.3 조건부 서류 체크리스트 (`rules/required_docs.py`)

R3.2의 핵심. 엔진의 `RequiredDocumentSpec`은 "택1 그룹" 개념이 없으므로 데모 측에서 조립한다.

```python
def build_checklist(program: ProgramConfig, applicant: ApplicantInput) -> list[DocRequirement]:
    """근로유형·선택항목에 따라 실제로 올려야 할 서류만 반환."""
```

두배적금 규칙:

| 입력 | 요구 서류 |
|---|---|
| 공통 (항상) | 초본, 건보 납부확인서, 건보 자격확인서, 건보 자격득실확인서, 행정정보공동이용동의서 |
| 근로유형 = 직장가입자 | + 4대보험 가입내역 확인서 (**4대보험 중 1개 이상 가입 시 반드시**) |
| 근로유형 = 직장가입자 AND 기간제(행정기관) | + 근로계약서 사본 |
| 근로유형 = 지역가입자·피부양자 | + 고용·산재보험 일용근로내역서 (미가입 시 예외적으로 근로계약서) |
| 근로유형 = 사업소득 사업자 | + 사업자등록**증명** |
| 근로유형 = 농업·임업 | + 농업경영체 증명서 |
| 근로유형 = 어업 | + 어업경영체 증명서 |
| 복수 사업장 근무 | 사업장별로 근로확인서류 각각 |

취업패키지 규칙: 공통(초본) + 선택 항목별 추가서류. 통장 사본은 계좌 입력으로 대체(R1.4).

### 3.4 DB 스키마

| 테이블 | 주요 컬럼 |
|---|---|
| `application` | id, application_no, program_code, status, applicant_json, self_check_json, created_at, submitted_at |
| `document` | id, application_id, doc_type, slot_key, file_path, file_format, declared_issue_date, ocr_json, stage1_status, findings_json, page_index |
| `consent` | id, application_id, consent_type, agreed, signature_path, agreed_at, client_ip, user_agent |
| `review` | id, application_id, final_status, score_json, total_score, review_payload_json, officer_role, officer_decision, officer_memo, decided_at |
| `subsidy_item` | id, application_id, item_type, receipt_amount, granted_amount, count_index  *(취업패키지 전용)* |

- `application_no`는 엔진 `Applicant.applicant_id` / `review_payload.applicant_id`와 **동일 키**를 쓴다. 담당자가 원본과 매칭하는 유일 키다.
- `document.slot_key`는 체크리스트의 슬롯 식별자(`work_proof`, `nhis_payment` 등). 같은 `doc_type`이 여러 슬롯에 올 수 있어 분리한다.
- `consent`에 `agreed_at` + IP + UA를 남기는 것이 "수기 서명 없이도 동의 증거를 남긴다"의 구현체다 (R1.1).

---

## 4. OCR 전략 — 3계층 어댑터

OCR은 현재 **아무도 구현하지 않은 공백**이다. 시연 안정성과 설득력을 동시에 확보하기 위해 3계층으로 나누고, 런타임에 폴백한다.

```python
# demo/backend/ocr/base.py
class OcrAdapter(Protocol):
    def read(self, file_path: str, expected: DocType) -> OcrResult: ...

@dataclass
class OcrResult:
    detected_doc_type: DocType | None
    confidence: float                     # 0.0 ~ 1.0
    image_quality: float
    issue_date: date | None
    has_signature: bool | None
    fields: dict[str, str]                # {"성명","가구원수","건강보험료","전입일",...}
    bboxes: dict[str, BBox]               # 필드 → 원본 좌표 (page, x0, y0, x1, y1)
    is_encrypted: bool
    is_screen_capture: bool               # 공고문 "모니터 화면 캡처 불인정"
    page_count: int
```

| Tier | 방식 | 대상 | 필수도 |
|---|---|---|---|
| 1. Fixture | `fixtures/` 샘플 파일명 → 사전 정의 판독 결과 | 시연 10종 시나리오 | **필수** |
| 2. PDF 텍스트 레이어 | PyMuPDF로 텍스트+좌표 추출 → 정규식으로 문서종류·발급일·가구원수·건보료·전입일 파싱 | 실제 정부24/건보공단 PDF | **권장** — "진짜 읽는다"를 증명 |
| 3. 상용 API | Upstage Document AI / 네이버 클로바 | 스캔 이미지(jpg/png) | 스텁만. TF 이후 |

**폴백 규칙**: Tier1 히트 → 반환. 미스 시 Tier2 시도. 텍스트 레이어 없음(스캔 이미지) → Tier3 미구성이면 `confidence = 0.0` → 엔진이 `NEEDS_REVIEW` → 담당자 큐. **데모가 멈추지 않는다.**

Tier2가 실제로 잘 동작한다. 정부24 발급 PDF는 이미지가 아니라 텍스트 PDF이고, 암호 여부(`fitz.open().needs_pass`)도 여기서 즉시 잡힌다.

**"모니터 화면 캡처" 탐지**: 이미지 EXIF에 카메라 정보가 없고 + 해상도가 흔한 화면 해상도(1920×1080, 2560×1440 등)에 근접하며 + 텍스트 레이어가 없으면 `is_screen_capture = True` → `NEEDS_REVIEW`. 확정 판정이 아니라 담당자 확인 대상으로 보낸다 (오탐 시 신청자가 억울해지는 항목이라 자동 반려하지 않는다).

**병합 PDF 자동 분리 (R3.5)**: 공고문은 "1개 파일로 압축"을 요구한다. 다중 페이지 PDF가 올라오면 페이지별로 Tier2 분류를 돌려 `document` 행을 페이지 단위로 나누고, 각 페이지를 체크리스트 슬롯에 자동 배정한다. 미배정 페이지는 담당자 확인 대상으로 남긴다.

---

## 5. 심사표 채점 (`rules/scoring.py`)

엔진에 점수 계산 기능이 **없다**. 추후 `engine/stage3_scoring.py`로 이관할 수 있도록 **순수 함수**로 작성한다.

```python
def score_application(facts: ScoringFacts, program: ProgramConfig) -> ScoreSheet: ...

@dataclass
class ScoreItem:
    label: str            # "도 거주기간"
    score: int            # 23
    max_score: int        # 25
    basis: str            # "2021-11-20 전입 → 공고일까지 4년 3개월"
    source_doc: DocType   # 주민등록초본
    bbox: BBox | None     # 담당자 화면 하이라이트용 (R4.3)
```

`ScoreSheet`가 항목별 `basis + source_doc + bbox`를 함께 담는 것이 이 설계의 핵심이다. "소득분위 초과"라고만 쓰면 담당자는 결국 원본을 뒤진다. 근거 문장과 좌표를 같이 넘기면 눈으로 3초 안에 검증된다.

### 5.1 중위소득 구간 판정

공고문은 **140% 표만** 제공한다. 심사표는 100/110/120/130% 구간을 요구하므로 환산이 필요하다.

```
소득기준(140%) 표의 건보료 → 100% 환산 = 값 × (100/140)
이후 110/120/130%는 100% 환산값에 비례 적용
```

예) 4인 직장가입자 140% = 311,031원 → 100% ≈ 222,165 / 110% ≈ 244,382 / 120% ≈ 266,598 / 130% ≈ 288,815

이 환산표는 **`(데모 추정치)` 라벨**을 코드 상수와 화면 양쪽에 단다. TF에서 원표를 받으면 상수 테이블만 교체한다 (Open Question 1).

판정 입력은 **건강보험 자격확인서상 가구원수** + **납부확인서상 '25.10~12월 고지금액 평균**이다 (실납부액 아님). 가입 유형(직장/지역/혼합)은 자격확인서의 직장가입자 칸 기재 여부로 구분한다.

### 5.2 동점자 정렬

목록 정렬 키로 구현한다: `(-total, 건보료평균 asc, 거주일수 desc, 근로일수 desc, 생년월일 desc)`.

---

## 6. 취업패키지 실비 계산 (`rules/subsidy.py`)

```python
LIMITS = {
    "interview":  ItemLimit(unit_cap=50_000, max_count=2, actual_cost=False),  # 정액 5만원/회
    "suit":       ItemLimit(unit_cap=50_000, max_count=2, actual_cost=True),
    "photo":      ItemLimit(unit_cap=20_000, max_count=1, actual_cost=True),
    "certificate":ItemLimit(unit_cap=50_000, max_count=2, actual_cost=True),
}

def granted(item, receipt_amount) -> int:
    return LIMITS[item].unit_cap if not LIMITS[item].actual_cost \
           else min(receipt_amount, LIMITS[item].unit_cap)
```

면접비만 **정액**(회당 5만원, 영수증 불요 — 면접확인서만), 나머지 3종은 **실비**(영수증 금액과 한도 중 작은 값)다. 자격증 응시확인서·성적표는 **응시일 표기가 필수**이므로 OCR에서 응시일 필드 부재 시 `FAIL`.

---

## 6-A. 서식 원형 재현 (R8)

### 6-A.1 무엇을 맞추는가

"서식 그대로"는 픽셀 복제가 아니라 **구조·순서·문구의 동형성**이다. 맞춰야 할 것은 셋이다.

1. **표 구조** — 좌측 항목 라벨열 + 우측 입력열, 병합 셀 구조
2. **항목 순서** — 서식에 적힌 순서 그대로 (재배열 금지)
3. **문구** — 항목명과 각주(`※ ...`)를 **원문 그대로**. 요약하거나 다듬지 않는다

### 6-A.2 `FormSheet` 컴포넌트 계층

```tsx
<FormSheet formNo="서식1" title="「전북청년 함께 두배적금」참여 신청서">
  <FormNotice>○ 빈칸에 기입하거나, □에 ✓(체크)표 하세요</FormNotice>

  <FormSection no="Ⅰ" title="기본정보">
    <FormRow label="인적사항" rowSpan={4}>
      <FormField name="name"      label="신청자 이름" />
      <FormField name="birthDate" label="생년월일" type="date" />
      <FormCheckGroup name="gender" options={['남','여']} inline />
    </FormRow>
    <FormRow label="전북특별자치도 거주기간"
             note="※ 전북특별자치도 최종전입일로부터 공고일(‘26. 3. 3.)까지 기간">
      <FormCheckGroup name="residencePeriod" readOnly derived
        options={['1년 미만','1년 이상 ~ 2년 미만', …]} />
    </FormRow>
  </FormSection>
</FormSheet>
```

- 레이아웃은 **CSS Grid**로 짠다. `<table>`은 셀 병합은 쉽지만 반응형 재배치(6-A.5)가 어렵다.
- 테두리 1px `#333`, 라벨 셀 배경 `#f2f2f2`, 본문 폰트는 맑은 고딕 계열 스택 — 관공서 서식의 시각적 관습을 따른다.
- `□`는 실제 `<input type="checkbox">`에 사각 테두리 스타일을 입혀 **모양은 서식, 동작은 웹**이 되게 한다.

### 6-A.3 위저드 vs 서식 — 충돌 해소 (핵심 판단)

R3(신청 쉽게)의 단계별 입력과 R8(서식 그대로)은 얼핏 충돌한다. **서식1이 이미 절(Ⅰ~Ⅳ) 구조를 갖고 있다**는 점을 이용하면 충돌하지 않는다. 위저드 스텝 경계를 **서식의 절 경계와 일치**시킨다.

| 스텝 | 서식1의 해당 구획 |
|---|---|
| Step 0 | (서식 상단) 저축목적 · 유사 자산형성사업 참여 여부 |
| Step 1 | Ⅰ. 기본정보 — 인적사항 · 비상연락망 |
| Step 2 | Ⅰ. 기본정보 — 전북특별자치도 거주기간 · 가구 및 소득 |
| Step 3 | Ⅰ. 기본정보 — 근로사항 |
| Step 4 | Ⅱ. 납입금액 · Ⅲ. 입금 받을 계좌 · Ⅳ. 기타사항 |

각 스텝은 **같은 `FormSheet`의 특정 구획만 보여주는 것**이고, 상단 "서식1 전체 보기" 토글을 켜면 전체가 한 장으로 펼쳐진다. 즉 스텝은 서식을 재구성한 것이 아니라 **스크롤 위치를 나눈 것**에 가깝다.

> 기존 계획의 Step1~4는 서식 절 순서와 미세하게 달랐다(저축목적이 Step4에 있었음). 위 표가 확정판이다.

### 6-A.4 자동계산과 서식 체크박스의 공존 (R8.5)

서식1은 거주기간을 **6구간 체크박스**로 받는다. 체크박스를 없애고 날짜 입력으로 바꾸면 서식이 깨지고, 체크박스만 두면 신청자가 잘못 고른다. 둘 다 둔다.

```
┌──────────────┬────────────────────────────────────────────────────┐
│ 전북특별자치도 │ 최종 전입일  [ 2021-11-20  📅 ]                     │
│ 거주기간      │ □1년 미만 □1~2년 □2~3년 □3~4년 ☑4~5년 □5년 이상   │
│              │ └ 2021-11-20 전입 → 공고일(2026.3.3.)까지 4년 3개월 │
│              │ ※ 전북특별자치도 최종전입일로부터 공고일까지 기간      │
└──────────────┴────────────────────────────────────────────────────┘
```

체크박스는 **읽기전용 + 자동 선택**이고, 선택 근거를 바로 아래 한 줄로 보여준다. 근로기간(4구간)·연령도 동일 패턴.

### 6-A.5 반응형 (R8.6)

A4 폭 고정 서식은 모바일에서 깨진다. 같은 컴포넌트가 두 레이아웃을 낸다.

| 폭 | 레이아웃 |
|---|---|
| ≥1024px | 서식 원본 그대로 — 라벨열 + 입력열 그리드 |
| <1024px | 항목 순서 유지한 채 **셀을 세로 스택** (라벨 위 / 입력 아래). 각주는 접힘 |

모바일에도 "서식 형태로 보기" 버튼을 둬서, 가로 스크롤로 원본 레이아웃을 확인할 수 있게 한다. 제출 직전 최종 확인 화면은 **폭과 무관하게 항상 서식 레이아웃**으로 보여준다 — 신청자가 "내가 낸 서류가 이렇게 생겼다"를 확인하는 지점이기 때문이다.

### 6-A.6 서식별 재현 범위

| 서식 | 원본 위치 | 재현 방식 |
|---|---|---|
| 서식1 참여신청서 | 시행지침 p13 | 절 단위 위저드 + 전체보기 토글 |
| 서식2 자가진단 | 시행지침 p14 상단 | `점검내용 | 확인·동의` 2열 표 그대로. 예/아니오 라디오. 6번 문항의 하위 ⑨개 제외대상은 접이식으로 원문 유지 |
| 서식3 개인정보 수집·이용 | 시행지침 p14 하단 | 고지문 **원문 그대로** + 동의 체크 2개(일반/고유식별정보) |
| 서식4 제3자 제공 | 시행지침 p15 상단 | 고지문 원문 + 동의 체크 1개 |
| 서식5 행정정보 공동이용 | 시행지침 p15 하단 | 표 그대로 + 서명란 자리에 **캔버스 전자서명** |
| 서식6 심사표 | 시행지침 p16 상단 | **담당자 화면**에 원본 배점표 레이아웃으로 렌더 (R8.7) |

> 서식6을 담당자 화면에 원본 표 형태로 그리는 것이 R8.7의 노림수다. 담당자가 쓰던 종이 심사표와 시각적으로 같으면 학습 비용이 0이고, "자동 채점을 믿어도 되나"라는 저항도 줄어든다. 자동 계산된 점수 칸에 배경색과 근거 문장만 얹는다.

> ⚠️ **원본 PDF가 2-up 레이아웃이다.** 시행지침·공고문 모두 물리 1페이지에 논리 2쪽이 들어 있다 (예: 시행지침 p13에 "- 23 -"과 "- 24 -"가 함께). 서식 캡처·좌표 작업 시 반드시 논리 쪽 경계를 기준으로 잘라야 한다.

---

## 6-B. 작성 서식의 PDF 내보내기 (R9 — 부가 기능)

작성 완료된 서식을 원본과 같은 형태의 PDF로 저장한다. **메인 기능이 아니다.** P7(선택)에 배치하고, 미구현이어도 DoD에 영향이 없다.

### 6-B.1 방식 비교

| 방식 | 내용 | 평가 |
|---|---|---|
| **A. 원본 PDF 오버레이** (권장) | 시행지침 PDF에서 서식 페이지를 떼어 템플릿으로 삼고, PyMuPDF `page.insert_text()` / `insert_image()`로 좌표에 값·체크·서명을 그려 넣음 | 결과물이 **원본과 100% 동일**. PyMuPDF는 이미 OCR Tier2 의존성이라 추가 없음. 단점: 필드별 좌표 맵을 수작업으로 떠야 함 |
| B. HTML → PDF | 화면의 `FormSheet`를 Playwright 또는 WeasyPrint로 인쇄 | 좌표 작업 불필요, 화면과 항상 일치. 단점: 한글 폰트 임베딩 필요, 헤드리스 브라우저 의존성 추가, 원본과 미세하게 다름 |

**A를 택한다.** 이 데모의 논점이 "행정 서식을 디지털로 옮겨도 서류로서 성립하는가"인데, A는 결과물이 기존 서식과 구분되지 않아 그 논점을 가장 강하게 보여준다. 의존성이 늘지 않는 것도 크다.

### 6-B.2 좌표 맵

```json
// demo/fixtures/form_coords/서식1.json
{
  "template": "templates/서식1.pdf",
  "logical_page": 0,
  "fields": {
    "name":        {"page": 0, "x": 148, "y": 232, "size": 10},
    "birthDate":   {"page": 0, "x": 280, "y": 232, "size": 10, "format": "%Y.%m.%d."},
    "gender.남":   {"page": 0, "x": 402, "y": 232, "type": "check"},
    "residencePeriod.4년 이상 ~ 5년 미만": {"page": 0, "x": 331, "y": 318, "type": "check"}
  }
}
```

- 좌표는 논리 쪽 기준. 2-up 원본은 **논리 쪽 단위로 미리 잘라** `demo/fixtures/templates/`에 넣어두고 쓴다.
- `type: "check"`는 해당 좌표에 `✓`를 찍는다.
- 서식5의 서명은 `type: "image"`로 캔버스 PNG를 서명란 좌표에 합성한다 (R9.2).

### 6-B.3 범위와 API

데모 구현 대상은 **서식1·서식5 2종만**이다. 서식5는 전자서명 합성이 들어가 "자필 없이도 서식이 완성된다"를 그대로 보여주므로 시연 가치가 가장 크다. 서식2~4는 좌표 맵만 비워둔 채 구조를 남긴다.

```
GET /api/applications/{id}/forms/{form_no}.pdf   → Content-Disposition: inline
```

담당자 심사 화면의 서류 탭에 **"작성 서식" 탭**을 추가해, 업로드 서류와 나란히 완성된 서식1·서식5를 브라우저 안에서 본다 (R9.3 — 여기서도 다운로드 0회를 지킨다).

---

## 7. API 설계

| Method | Path | 설명 |
|---|---|---|
| `GET` | `/api/programs` | 사업 목록 + 신청기간 + 정원 |
| `POST` | `/api/applications` | 신청 생성(임시저장), 신청번호 발급 |
| `PATCH` | `/api/applications/{id}` | 단계별 부분 저장 (R3.4) |
| `POST` | `/api/applications/{id}/self-check` | 자가진단 채점 → 부적격 사유 + 대안 안내 |
| `GET` | `/api/applications/{id}/required-documents` | **맞춤 서류 체크리스트** (R3.2) |
| `POST` | `/api/applications/{id}/documents` | 파일 + `declared_issue_date` → **즉시 1단계 판정 반환** (R2.1) |
| `DELETE` | `/api/applications/{id}/documents/{doc_id}` | 재업로드용 삭제 |
| `POST` | `/api/applications/{id}/consents` | 동의 체크 + 전자서명 저장 (R1.1/R1.2) |
| `POST` | `/api/applications/{id}/subsidy-items` | 취업패키지 항목 선택 + 영수증 금액 |
| `POST` | `/api/applications/{id}/submit` | 최종 제출 → 전체 파이프라인 + 심사표 채점 |
| `GET` | `/api/applications/{id}/status` | 마이페이지 (**점수 미포함**, R5.3) |
| `GET` | `/api/officer/applications` | 담당자 목록 (필터·정렬·페이징) |
| `GET` | `/api/officer/applications/{id}` | 심사 상세 (`review_payload` + `ScoreSheet` + bbox) |
| `GET` | `/api/files/{doc_id}` | **인라인** 스트리밍 (`Content-Disposition: inline`) (R4.1) |
| `POST` | `/api/officer/applications/{id}/decision` | 승인/반려/보류 + 메모 + 역할 |
| `GET` | `/api/applications/{id}/forms/{form_no}.pdf` | **작성 서식 PDF 내보내기** (R9, P7 선택) — 인라인 |

### 업로드 응답 예시 (R2.2)

```json
{
  "document_id": "DOC-8821",
  "slot_key": "resident_abstract",
  "detected_doc_type": "주민등록등본",
  "status": "FAIL",
  "findings": [{
    "code": "WRONG_DOCUMENT_TYPE",
    "message": "주민등록 '초본'을 올려야 하는데 '등본'이 업로드되었습니다.",
    "how_to_fix": "정부24에서 '주민등록표 초본'을 발급하세요. 발급 시 ① 주민등록번호 뒷자리 표시 ② 최근 5년 주소변동내역 포함을 반드시 체크해야 합니다.",
    "link": "https://www.gov.kr"
  }],
  "extracted": {"성명": "홍길동", "발급일": "2026-03-05"},
  "ocr_confidence": 0.94,
  "elapsed_ms": 1180
}
```

---

## 8. 엔진 연동 (`engine_adapter.py`)

현재 엔진 스키마와 공고문 실제값이 어긋난다. 어댑터가 그 간극을 흡수한다.

| 엔진이 기대하는 것 | 데모가 가진 것 | 어댑터 처리 |
|---|---|---|
| `income_decile: int` (1~10) | 중위소득 % (건보료 기준) | 중위소득 %를 10분위로 근사 매핑. **엔진이 `income_ratio`를 받도록 수정되면 제거** |
| `REQUIRED_DOCUMENTS` 에 `주민등록등본` | 필수는 **초본** | 어댑터에서 `config.REQUIRED_DOCUMENTS` 런타임 오버라이드 |
| `DOCUMENT_ISSUE_CUTOFF = 2026-08-01` | 두배적금 2026-03-03 / 취업패키지 2026-01-01 | 런타임 주입 |
| `review_payload.documents[].file_ref` = null | 원본 파일 있음 | `/api/files/{doc_id}` URL 주입 |
| 점수 계산 없음 | 심사표 100점 필요 | 데모 `rules/scoring.py`가 담당 |

> 어댑터는 **런타임 오버라이드**로 시작하고, 진과 합의되는 항목부터 엔진 본체로 옮긴다. 엔진 수정을 기다리느라 데모가 막히지 않게 하는 것이 목적이다.

---

## 9. 엔진 측 수정 요청 (진과 공유)

| # | 현재 엔진 | 공고문 실제값 | 영향 |
|---|---|---|---|
| E1 | 필수서류에 `주민등록등본` | **주민등록초본** (공고문 "※등본 아님") | 라벨이 정반대. 최우선 |
| E2 | `소득금액증명원`, `건강보험료납부확인서` | 소득재산 증빙 **3종**(납부확인서/자격확인서/자격득실확인서) | 필수서류 목록 재정의 |
| E3 | 근로확인서류 없음 | **5종 중 택1** (조건부 필수) | `RequiredDocumentSpec`에 "택1 그룹" 개념 필요 |
| E4 | `행정정보공동이용동의서` 서명 필요 | 동일 (유일하게 일치) | 전자서명 시 `has_signature` 판정 방식 협의 |
| E5 | `DOCUMENT_ISSUE_CUTOFF = 2026-08-01` | 두배적금 **2026-03-03**, 취업패키지 **2026-01-01** | 상수 교체 |
| E6 | `income_decile` (1~10분위) | **중위소득 %** (가구원수 × 건보료 고지금액) | `Applicant` 스키마 변경 |
| E7 | `INCOME_DECILE_LIMIT = 9` | 중위소득 **140% 이하** | 판정 로직 변경 |
| E8 | 취업패키지 = 등본/졸업증명서/참여동의서 | 초본 + 계좌 + 항목별 추가서류 | 전면 교체 |
| E9 | 점수 계산 없음 | 심사표 100점 | `stage3_scoring` 신설 또는 데모 보유 |
| E10 | 혼동군에 등본/초본 | 유지하되 필수를 **초본**으로 반전. `사업자등록증 ↔ 사업자등록증명` 쌍 추가 | 오분류 탐지 |
| E11 | `CONFLICTING_BENEFIT_PROGRAMS = {"청년수당"}` | 제외대상 **8개 카테고리** (유사 자산형성 20+종, 공무원, 병역, 사행업, 중도해지자 등) | 대폭 확장 |
| E12 | 보완 정책 단일 | 두배적금 **보완 불가** vs 취업패키지 **7일 보완** | 사업별 분기 |
| E13 | `TARGET_REGIONS` (시군 집합만) | 시군별 **정원**까지 필요 (전주 550 … 진안 15) | 정원 데이터 추가 |

> **연동 규약 제안**: `doc_type` 문자열을 `engine/doc_types.py` 단일 소스로 두고 데모·엔진·대시보드가 import한다. 문자열 불일치가 가장 흔한 사고 지점이다.

---

## 10. 디렉토리 구조

> ★ **생성하는 모든 파일은 저장소 루트에 새로 만드는 `demo/` 폴더 안에만 둔다.**
> 루트·`engine/`·`dashboard/`에는 파일을 추가하거나 수정하지 않는다 (C1). 예외는 `.gitignore` 4줄 추가와 `docs/demo-site-dev-plan.md` 갱신뿐이다.
> 백엔드·프론트엔드를 각각 루트에 두지 않고 `demo/` 하위로 묶는 이유: 저장소가 3인 공동 작업(engine/dashboard/demo)이라 최상위 이름 충돌과 의존성 파일(`package.json`, `requirements.txt`) 경합을 원천 차단한다.

```
2026-2-capstone/
├── engine/                          # 진 담당 — 읽기만, 수정 안 함
├── dashboard/                       # 채운 담당 — 건드리지 않음
├── docs/demo-site-dev-plan.md       # 대외 공유용 계획서
├── .gitignore                       # demo/storage/, demo/**/*.db, node_modules, dist 추가
│
└── demo/                            ★ 이 태스크의 유일한 작업 영역
    ├── README.md
    ├── backend/
    │   ├── main.py
    │   ├── reset.py                 # 시연 초기화
    │   ├── models.py                # SQLModel
    │   ├── engine_adapter.py        # 엔진과의 유일한 접점
    │   ├── requirements.txt
    │   ├── api/                     # applications · documents · consents · review · files
    │   ├── ocr/                     # base · fixture · pdftext · upstage(stub)
    │   └── rules/                   # programs · doc_types · required_docs · scoring · subsidy
    ├── frontend/
    │   ├── package.json             # 루트가 아닌 여기에 둔다 (dashboard/package.json과 분리)
    │   ├── vite.config.ts
    │   └── src/
    │       ├── pages/applicant/     # SelfCheck · Form · Consent · Upload · Review · MyPage
    │       ├── pages/officer/       # Inbox · ReviewDetail
    │       └── components/          # DocumentUploader · PdfViewer · ScoreCard · SignaturePad
    ├── fixtures/                    # 시연 샘플 서류 + 기대 판독 결과 JSON (더미만)
    │   ├── templates/               # 원본 PDF에서 논리 쪽 단위로 자른 서식 (서식1·서식5)
    │   └── form_coords/             # 서식별 필드 좌표 맵 JSON (R9, P7)
    ├── storage/                     # 업로드 원본 (gitignore)
    └── demo.db                      # SQLite (gitignore)
```

**엔진 import 경로**: `demo/backend`는 저장소 루트를 `sys.path`에 올려 `from engine.pipeline import run_pipeline`으로 접근한다. `engine/`을 `demo/` 안으로 복사하지 않는다 — 진의 수정이 그대로 반영되어야 한다.

---

## 11. 설계상 트레이드오프

| 결정 | 대안 | 선택 이유 |
|---|---|---|
| 엔진을 프로세스 내 import | 별도 서비스로 HTTP 호출 | 데모에 운영 복잡도를 더할 이유가 없다. 어댑터 한 파일이 경계를 지킨다 |
| 점수 계산을 데모에 둠 | 엔진 `stage3_scoring` 신설 대기 | 엔진 수정 일정에 데모가 종속되면 안 된다. 순수 함수로 짜서 나중에 그대로 이관 |
| 전자서명으로 자필 대체 | 자필 스캔 업로드 유지 | "수기 0건"이 이 데모의 논점이다. 다만 현행 지침 위반이므로 배지로 드러내고 자필 모드도 토글로 남긴다 |
| SQLite | PostgreSQL | 시연 리셋과 배포 단순성 |
| 화면캡처 탐지를 `NEEDS_REVIEW`로 | `FAIL` | 오탐 시 신청자 피해가 크다. 사람이 최종 판단 |
| bbox를 OCR 결과에 포함 | 판정 사유 텍스트만 | R4.3이 담당자 화면의 유일한 차별점이다. bbox 없이는 결국 원본을 뒤진다 |
| 서식 원형을 CSS Grid로 재현 | 일반 웹 폼으로 재구성 | 담당자가 종이 서식과 1:1 대조 가능해야 하고, 신청자도 공고문을 보며 따라갈 수 있다. 재구성하면 둘 다 깨진다 |
| 위저드 스텝 = 서식 절 경계 | 서식 전체를 한 화면에 / 임의 스텝 분할 | 한 화면은 모바일에서 무너지고, 임의 분할은 서식 구조를 깬다. 절 경계는 원본이 이미 제공하는 분할선이다 |
| PDF 내보내기 = 원본 오버레이(PyMuPDF) | HTML→PDF (Playwright/WeasyPrint) | 결과물이 원본과 구분되지 않는 것이 이 데모의 논점에 직결. 의존성도 늘지 않는다. 좌표 수작업은 2종만 하므로 감당 가능 |

---

## 12. 리스크

| 리스크 | 영향 | 대응 |
|---|---|---|
| 실물 서류 샘플 미확보 (청년허브센터 지급 예정) | fixture 제작 불가 | 공개 서식으로 자체 제작, 실물 확보 시 교체. **개인정보 없는 더미만** |
| 중위소득 100~130% 건보료 원표 미확보 | 심사표 40점 항목 부정확 | 140% 표 선형 환산 + `(데모 추정치)` 라벨 |
| 전자서명이 현행 지침 위반 | 시연 중 지적 | "제도 개선 제안" 배지 + 자필 모드 토글 병행 |
| OCR 오판독 | 시연 중 사고 | Tier1 fixture가 기본 경로. 실패 시 `NEEDS_REVIEW`로 안전 강등 |
| 엔진 스키마 변경 지연 | 업로드·판정 착수 불가 | `engine_adapter.py` 런타임 오버라이드로 독립 진행 |
| 대시보드와 담당자 화면 중복 | 작업 낭비 | 경계 확정: 데모=건별 심사, 대시보드=집계·통계 |
| 개인정보 취급 | 법적 리스크 | 더미 데이터만. 서류 파일·DB 커밋 금지 |
