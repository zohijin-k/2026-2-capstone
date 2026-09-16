# 담당자 화면 목업 데이터

담당자 심사 화면(`/` → 담당자 탭)은 접수된 신청 건이 하나도 없으면 빈 표가 된다.
시연에서 "다양한 사람이 신청하면 이렇게 보인다"를 보여주려면 데이터를 넣어야 하는데,
방법이 셋이다. **현재 구현된 것은 1번(프론트엔드 하드코딩)**이고, 2·3번은 나중에
필요해질 때를 위해 방법만 적어 둔다.

| | 방식 | 목록·정원·필터 | 건별 심사표 | 원본 뷰어·bbox | 승인/반려 영속 | 준비 비용 |
|---|---|---|---|---|---|---|
| 1 | 프론트엔드 하드코딩 **(현재)** | O | O | 대역 이미지 | 브라우저 메모리 | 없음 |
| 2 | 실제 신청 플로우로 시드 | O | O | O (실제 PDF) | O (DB) | 샘플 PDF 생성 + 수십 초 |
| 3 | DB에 직접 삽입 | O | O | X | O (DB) | 중간 |

---

## 1. 프론트엔드 하드코딩 — 현재 구현

파일: [`demo/frontend/src/pages/officer/mock-data.ts`](../frontend/src/pages/officer/mock-data.ts)

### 켜지는 조건

`demo/frontend/src/api.ts`의 담당자 API 래퍼가 전환한다.

- `?mock=1` — 강제로 켠다. 백엔드가 떠 있어도 목업을 본다.
- **자동** — 담당자 목록 API가 실패했거나 접수 건이 **0건**일 때 목업으로 넘어간다.
  필터를 걸어서 0건인 경우는 해당하지 않는다(실제로 그 조건에 건이 없는 것이다).
- `?mock=0` — 어떤 경우에도 목업을 쓰지 않는다. 실제 접수가 0건인 것을 확인해야 할 때.

목업이 켜지면 화면 상단에 노란 배너가 뜬다. 시연을 보는 사람이 실제 접수 건으로
오해하지 않게 하는 장치라 지우지 않는다.

### 무엇이 들어 있나

행을 손으로 적지 않고 **고정 시드 난수**로 만든다. 시군별 정원 대비 진행률과
커트라인이 뜻을 가지려면 2천 건 규모가 필요한데 손으로는 못 적는다. 시드가 고정이라
새로고침해도 같은 화면이 나온다 — 시연 대본을 쓸 수 있다.

- 두배적금 약 1,500건 — 시군별 배정 인원 × 접수 배수(도시 1.0~1.35배, 군 지역 0.5~0.9배)
- 취업지원패키지 612건 — 선착순 총 900건의 68%
- 14개 시군 × 읍·면·동, 30개 성 × 50개 이름 조합
- 점수는 배점 구간(`rules/scoring.py`)을 그대로 적용해 산출. 만점 25명, 90점대가 최빈
- AI판정 적합 85% / 부적합 7% / 확인필요 8%, 미비서류 0~3건
- 약 28%는 이미 처리됨(서류 완비 확인·1차 선발·보류·반려)

### 동작하는 것 / 안 하는 것

동작한다:

- 역할 전환 3계층(읍·면·동 → 시군 → 도)과 역할별 보이는 범위·가능한 액션
- 사업·시군·읍면동·처리상태·AI판정·신청일 필터, 점수순/접수순 정렬, 페이지네이션
- 시군별 정원 대비 진행률 배지와 커트라인(120% / 100%), 선착순 사업 접수 진행률 배지
- 건별 심사표(서식6) 4항목과 근거 문장, 자격요건·제외대상 체크리스트
- 승인·반려·보류(일괄 포함) — **브라우저 메모리에만** 남는다. 새로고침하면 되돌아간다
- 근거 클릭 → 좌측 원본 하이라이트. 원본은 신청자 판독값을 박아 만든 **대역 SVG**다

동작하지 않는다:

- 실제 업로드 PDF·OCR 결과 (대역 이미지로 갈음)
- 작성 서식 PDF 내보내기 탭 (`forms`는 빈 배열)
- 판단의 DB 영속

### 상수를 서버와 맞춰야 한다

`mock-data.ts`는 시군별 정원·배점 구간·동점자 키·역할 정의를 **서버에서 복사해**
들고 있다. 아래 파일이 바뀌면 목업도 같이 고쳐야 한다. 어긋나면 목업을 보고 내린
판단이 실제와 달라진다.

- `demo/backend/rules/programs.py` — `DOUBLE_SAVINGS_QUOTA`, 총 지원 규모
- `demo/backend/rules/scoring.py` — `INCOME_BANDS` / `RESIDENCE_BANDS` / `WORK_BANDS` / `AGE_BANDS` / `tiebreak_key`
- `demo/backend/rules/roles.py` — `ROLES` (역할명·단계·액션 라벨)
- `demo/backend/api/officer.py` — `LIST_COLUMNS`, `AI_STATUS_LABELS`, 필터 적용 순서

---

## 2. 실제 신청 플로우로 시드 (미구현)

신청자 화면이 하는 일을 스크립트가 API로 그대로 수행한다. **화면의 모든 기능이
실제로 동작하는** 유일한 방법이다 — 원본 PDF가 실제로 있고, OCR이 실제로 돌고,
bbox가 실제 판독 좌표이고, 승인/반려가 DB에 남는다.

`demo/backend/tests/run_p4_scenarios.py`의 `seed()`가 이미 이 일을 4건 규모로 한다.
시드 스크립트는 그것을 규모만 키운 것이 된다.

### 방법

1. 샘플 PDF를 만든다 (저장소에 커밋되지 않는다).

   ```bash
   PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -m demo.fixtures.make_samples
   ```

2. `demo/backend/seed.py`를 새로 만들어, 건마다 아래를 호출한다.

   ```
   POST  /api/applications                       사업 선택
   PATCH /api/applications/{id}                  서식1 (이름·주소·생년월일·취업일…)
   POST  /api/applications/{id}/self-check       서식2 자가진단
   POST  /api/applications/{id}/consents         서식3·4·5 동의 + 전자서명
   PUT   /api/applications/{id}/doc-context      근로유형·사업장 수
   POST  /api/applications/{id}/documents        구비서류 업로드 (슬롯별)
   POST  /api/applications/{id}/submit           제출 → 엔진 파이프라인 + 채점
   ```

3. `fastapi.testclient.TestClient(app)`을 쓰면 서버를 띄우지 않고 같은 경로를 탄다
   (P4 검증 스크립트와 같은 방식). 다만 **`demo/demo.db`와 `demo/storage/`를 실제로
   건드리므로** 시드 전용임을 스크립트 상단에 명시하고, 되돌리기는
   `python -m demo.backend.reset`으로 한다.

### 주의할 점

- **점수가 잘 안 벌어진다.** 소득(40점)과 거주기간(25점)은 초본·납부확인서 **판독값**이
  근거라(`rules/facts.py`: 서류 판독값 우선) 같은 샘플 파일을 쓰면 전건이 같은 값이 된다.
  변별력은 서식1에서 오는 연령(10점)·근로기간(25점)뿐이다. 점수를 벌리려면 소득·전입일이
  다른 샘플 PDF를 여러 벌 만들어야 한다.
- 건당 업로드 5건 + OCR + 파이프라인이라 수백 건이면 수십 초~수 분 걸리고,
  `demo/storage/`에 파일이 그만큼 쌓인다.
- 시군별 정원(전주 550명)을 채우려면 수천 건이 필요한데, 그 규모는 이 방식으로는
  현실적이지 않다. 정원 배지를 실감나게 보여주는 것이 목적이면 1번이나 3번이 맞다.

---

## 3. DB에 직접 삽입 (미구현)

`Application` + `Review` 행을 만들어 `demo/demo.db`에 바로 넣는다. 업로드·OCR을
건너뛰므로 수천 건도 순식간이고, 점수 분포를 원하는 대로 만들 수 있다. 판단이 DB에
남는 것도 1번과 다른 점이다.

### 방법

```python
from demo.backend.models import Application, Review, get_session, STATUS_SUBMITTED
from demo.backend.rules.scoring import ScoringFacts, score_application, tiebreak_key
from demo.backend.rules.programs import DOUBLE_SAVINGS, get_program

program = get_program(DOUBLE_SAVINGS)
facts = ScoringFacts(
    household_size=4, monthly_premium=240_000, insurance_type="직장",
    transfer_in_date=date(2019, 4, 2), employment_date=date(2022, 8, 1),
    birth_date=date(1996, 5, 12),
)
sheet = score_application(
    facts,
    announcement_date=program.announcement_date,
    age_basis_date=program.age_basis_date,
)

with get_session() as s:
    app = Application(
        application_no="DS-2026-000001",
        program_code=DOUBLE_SAVINGS,
        status=STATUS_SUBMITTED,
        form1_json={"name": "홍길동", "address": "전북특별자치도 전주시 완산구 효자동 123", ...},
        self_check_json={str(i): "예" for i in range(1, 9)},
        submitted_at=datetime(2026, 3, 5, 9, 12),
    )
    s.add(app); s.commit(); s.refresh(app)
    s.add(Review(
        application_id=app.id,
        final_status="PASS", stage1_status="PASS", stage2_status="PASS",
        score_json=sheet.as_dict(), total_score=sheet.total, tiebreak_json=sheet.tiebreak,
        review_payload_json={...},   # 담당자 화면의 '최종 판정' 패널이 읽는다
    ))
    s.commit()
```

### 주의할 점

- **미비서류 수가 전건 부풀려진다.** `api/officer._missing_count()`가 체크리스트의
  필수 슬롯을 훑는데 `Document` 행이 하나도 없으므로 필수 서류 수(두배적금 5건)가
  그대로 미비 수가 된다. 목록의 "미비서류" 컬럼이 전부 5가 된다.
- **건별 원본 뷰어가 빈 화면이 된다.** 심사 상세는 `documents[0]`이 없으면
  "심사 정보를 불러오는 중…"에서 멈춘다(`ReviewDetail.tsx`의 `if (!detail || !activeDoc)`).
  최소 1건의 `Document` 행과 실제로 열리는 `file_path`가 필요하다.
- 시군·읍면동은 `form1_json["address"]` 문자열에서 파싱된다(`rules/facts.extract_region`).
  주소 문자열이 `전북특별자치도 {시군} {읍면동} {번지}` 꼴이어야 목록 컬럼이 채워진다.
- 신청번호는 `api/applications._next_application_no()`가 전체 건수로 매기므로, 직접
  삽입한 건과 화면에서 만든 건의 번호가 겹칠 수 있다. 시드는 별도 접두어를 쓰는 편이 안전하다.
