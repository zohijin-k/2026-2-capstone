# 실행 계획 — 담당자 목록 서류 컬럼 + 상세 점프

순서의 이유: **계약 → 백엔드 → 화면 → 목업 → 문서**. 계약(타입)을 먼저 못 박아야
백엔드와 목업이 같은 모양을 낸다. 목업을 마지막에서 두 번째에 두는 것은, 그 전까지
`?mock=0`으로 실데이터를 보며 검증하고 목업은 그 결과에 맞추기 위해서다.

## 단계 0 — 기준선 확인

- [x] 0.1 `cd demo/frontend && npx tsc -p tsconfig.app.json --noEmit` — 지금 통과하는지 먼저 본다
- [x] 0.2 `cd demo/frontend && npm run lint`
- [x] 0.3 저장소 루트에서 `PYTHONUTF8=1 python -m demo.backend.tests.run_p4_scenarios`
- [x] 0.4 셋 중 이미 깨진 것이 있으면 **거기서 멈추고** 기존 실패인지 확인한다.
      이번 변경의 실패와 섞이면 되돌릴 자리를 못 찾는다.

> 작업 트리에 이미 미커밋 변경 9개가 있다 (`demo/backend/main.py`,
> `demo/frontend/src/pages/officer/*` 포함). 이번 작업과 섞이므로 0단계 기준선은
> **현재 작업 트리** 기준이다.

## 단계 1 — 타입 계약 (`demo/frontend/src/api.ts`)

- [x] 1.1 `OfficerRowDoc` 인터페이스 추가 (design.md §2.2 그대로)
- [x] 1.2 `OfficerRow`에 `documents?: OfficerRowDoc[]` 추가 — **옵셔널**이다 (design.md §6)
- [x] 1.3 주석에 "왜 배열인가"(기타 칸 복수)와 "왜 옵셔널인가"(구버전 응답 내성)를 남긴다
- [x] 검증: `npx tsc -p tsconfig.app.json --noEmit` — 이 단계만으로는 아무것도 안 깨져야 한다

## 단계 2 — 백엔드 서류 칸

### 2.1 `demo/backend/api/common.py`

- [x] `list_documents_bulk(application_ids) -> dict[int, list[Document]]` 추가
- [x] 빈 리스트가 들어오면 빈 dict를 즉시 반환 (`IN ()` 쿼리 방지)
- [x] 기존 `list_documents`는 **지운다/바꾸지 않는다** — 상세 화면이 계속 쓴다

### 2.2 `demo/backend/api/officer.py`

- [x] 2.2.1 `DOC_COLUMNS` (slot_key, 헤더 표기) 5쌍 + `OTHER_DOC_COLUMN` 상수
- [x] 2.2.2 `DOC_SHORT_BY_TYPE` (DocType → 짧은 이름) — design.md §2.3
- [x] 2.2.3 `_missing_count(app)` → `_doc_cells(app, documents)` 로 교체.
      반환 `(cells, missing)`. 미비 개수의 **정의는 그대로 유지**한다
      (안 올린 필수 + PASS 아님 + 미배정 페이지)
- [x] 2.2.4 `_columns(program)` — 두배적금/전체에는 서류 컬럼을 `missing_count` 뒤에 끼우고,
      `job_package`에는 기존 `LIST_COLUMNS`를 그대로 준다
- [x] 2.2.5 `_row(entry, rank, documents)` 시그니처 변경 — 서류를 인자로 받는다.
      `program_code != DOUBLE_SAVINGS`이면 `documents: []`
- [x] 2.2.6 `list_applications`에서 **window 행만** `list_documents_bulk`로 한 번에 읽고
      `_row`에 넘긴다. 응답의 `"columns"`를 `_columns(program)`으로 바꾼다
- [x] 검증: `python -m demo.backend.tests.run_p4_scenarios` (기존 6개 시나리오가 그대로 통과)
- [x] 검증: 실행 중인 데모에서 `curl 'localhost:8000/api/officer/applications?role=province' | python -m json.tool`
      → `columns`에 `doc:` 6개, 두배적금 행에 `documents` 6칸

> **리뷰 게이트 A**: 여기서 한 번 멈춘다. `missing_count`와 `documents`가 **같은
> 함수에서** 나오는지, 미비 개수가 변경 전과 **같은 값**인지 확인한다. 값이 달라졌다면
> 정의를 건드린 것이고, 그건 이 작업의 범위가 아니다.

## 단계 3 — 목록 화면

### 3.1 `demo/frontend/src/pages/officer/ApplicationList.tsx`

- [x] 3.1.1 `DocCell` 컴포넌트 — design.md §4.1의 표 그대로
- [x] 3.1.2 `Cell`에서 `switch` **앞에** `doc:` 접두사 분기
- [x] 3.1.3 `Props.onOpen`을 `(applicationId, slotKey?) => void`로 넓힘
- [x] 3.1.4 `onClick`에 `e.stopPropagation()` — 없으면 R2.3이 깨진다
- [x] 3.1.5 미제출 칸은 `<button disabled>`가 아니라 **버튼이 아닌 요소**로 둔다
      (탭 순서에 빈 칸이 6개씩 끼면 키보드 이동이 못 쓰게 된다)
- [x] 3.1.6 빈 표의 `colSpan={list.columns.length + 2}`는 `columns`를 세므로 그대로 맞는다 — 확인만

### 3.2 `demo/frontend/src/pages/officer/officer.css`

- [x] 3.2.1 `.grid__doc`, `.docdot--pass/--review/--fail/--none`, `.docdot__name`, `.grid__doc-na`
- [x] 3.2.2 점 색은 `format.ts:dotClass`가 쓰는 기존 상태 색과 **같은 값**을 쓴다
- [x] 3.2.3 표가 넓어진 만큼 `.grid` 가로 스크롤이 필요한지 확인하고, 필요하면 래퍼에 `overflow-x`

### 3.3 `demo/frontend/src/pages/officer/ReviewDetail.tsx`

- [x] 3.3.1 `initialSlotKey?: string | null` 프롭
- [x] 3.3.2 `load()`의 초기 탭 선택을 `slot_key` 우선 → 없으면 첫 서류(현행)
- [x] 3.3.3 뷰어·탭·하이라이트 로직은 **건드리지 않는다** (R5.2)

### 3.4 `demo/frontend/src/pages/officer/OfficerConsole.tsx`

- [x] 3.4.1 `openId` → `open: { id, slot } | null`
- [x] 3.4.2 `onOpen={(id, slot) => setOpen({ id, slot: slot ?? null })}`
- [x] 3.4.3 `<ReviewDetail key={...} initialSlotKey={open.slot} />`
- [x] 3.4.4 `onBack`, `switchRole`에서 `setOpen(null)` — 기존 `setOpenId(null)` 자리 전부

- [x] 검증: `npx tsc -p tsconfig.app.json --noEmit` / `npm run lint`
- [x] 검증(실데이터): P4 픽스처 API 응답으로 AC1·AC2·AC3·AC4·AC5·AC7 확인 (브라우저 육안 확인은 미실시)

## 단계 4 — 목업

`demo/frontend/src/pages/officer/mock-data.ts`. design.md §5.

- [x] 4.1 `WorkCategory` 5종 상수 + `WORK_PROOF_BY_CATEGORY`(슬롯 라벨·짧은 이름·판독 필드)
- [x] 4.2 `MockEntry`에 `workCategory` 추가, `makeSavingsEntry`에서 `insuranceType`과
      모순 없이 뽑는다
- [x] 4.3 `makeSavingsEntry`의 서류 1장 → **5종**. 판독값은 기존 사실값
      (`birth`/`address`/`transferIn`/`employedAt`/`householdSize`/`monthlyPremium`)에서 나온다
- [x] 4.4 `DOC_TYPE_TO_SLOT` 매핑으로 `FAIL_REASONS`/`REVIEW_REASONS`를 해당 서류에 얹는다
- [x] 4.5 ~12% 확률로 서류 1종 미제출
- [x] 4.6 `missing_count`·`aiStatus`를 서류에서 **역산** (난수 `missing` 제거)
- [x] 4.7 `LIST_COLUMNS`에 서류 컬럼 6개 추가 (`FIRST_COME_COLUMNS`는 건드리지 않는다)
- [x] 4.8 `mockOfficerList` 행에 `documents` 채우기 — 백엔드 `_doc_cells`와 **같은 규칙**
- [x] 4.9 `mockReviewDetail`의 `abstractDoc` 조회가 이제 두배적금에서도 값을 찾는다.
      자격요건 `basis` 문구가 이상해지지 않는지 확인

- [x] 검증: `npx tsc -p tsconfig.app.json --noEmit` / `npm run lint`
- [x] 검증(목업): 목업 모듈을 node로 직접 돌려 AC1~AC5·AC7 확인 (브라우저 육안 확인은 미실시)
- [x] 검증: 두배적금 상세 좌측 탭이 5개인지, 목록에서 누른 서류가 열리는지

> **리뷰 게이트 B**: 목업과 실데이터를 **나란히** 연다 (`?mock=1` / `?mock=0`).
> 컬럼 개수·순서·라벨·점 색이 같아야 한다. 다르면 목업의 쓸모가 없어진다.

## 단계 5 — 문서

- [x] 5.1 `demo/docs/officer-mock-data.md` — "무엇이 들어 있나"(32행 부근)와
      "목록 화면도 사업에 따라 달라진다"(73행 부근), "상수를 서버와 맞춰야 한다"(142행 부근)에
      서류 5종·근로유형 분포·서류 컬럼을 반영
- [x] 5.2 `demo/README.md`에 담당자 목록 설명이 있으면 갱신 (없으면 넘어감)

## 단계 6 — 최종 검증 (AC 전수)

- [x] AC1 두배적금 목록에 서류 컬럼 6개
- [x] AC2 근로유형 다른 두 행의 `근로확인서류` 칸 서류명이 다름
- [x] AC3 미제출 칸이 구분되어 보임
- [x] AC4 `미비서류` 숫자 = 서류 칸의 (미제출 + 적합 아님) 개수 — **행 3개 이상 직접 세어 본다**
- [x] AC5 서류 칸 클릭 → 상세가 그 서류 탭으로 열림
- [x] AC6 미제출 칸 클릭 무반응, 행 클릭으로 번지지 않음 — **마크업 수준 확인**: 미제출은 `<span>`(핸들러 없음), 서류 `<td>`가 `stopPropagation`
- [x] AC7 취업패키지 필터에서 기존 `신청 항목` 컬럼셋 유지
- [x] AC8 `?mock=1` 경로 데이터에서 AC1~AC5 재현 (node 실행 확인)
- [x] AC9 `?mock=0` 경로 데이터에서 AC1~AC5 재현 (TestClient 확인)
- [x] AC10 `npx tsc -p tsconfig.app.json --noEmit` · `npm run lint` · `run_p4_scenarios` 통과
- [x] AC11 `grep -rn "attachment\|download" demo/frontend/src demo/backend` — 새로 생긴 것 없음

## 되돌리기 지점

| 지점 | 되돌리는 것 | 남는 것 |
|---|---|---|
| 단계 6 실패 | 단계 3~4 | 백엔드 `documents` 필드 (화면이 안 읽으면 무해) |
| 게이트 B 실패 | 단계 4만 | 실데이터 화면은 그대로 동작 |
| 게이트 A 실패 | 단계 2만 | 타입만 늘어난 상태 (무해) |
| 전체 | `git checkout -- demo/` **위험** | 작업 트리에 이번 작업과 무관한 미커밋 변경 9개가 있다. 파일 단위로 되돌린다 |

## 검증 명령 모음

```bash
# 프론트
# 주의: 루트 tsconfig.json은 `"files": []` + 프로젝트 참조라 `tsc --noEmit`만 쓰면
# **아무 파일도 검사하지 않고** 통과한다. 반드시 -p 로 앱 프로젝트를 지정한다.
cd demo/frontend && npx tsc -p tsconfig.app.json --noEmit && npm run lint && npm run build

# 백엔드 시나리오 (저장소 루트에서)
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -m demo.backend.tests.run_p4_scenarios

# 목록 응답 눈으로 확인
curl -s 'http://localhost:8000/api/officer/applications?role=province' | python -m json.tool | head -60
```

## 남은 것

브라우저에서 두 화면을 **눈으로** 보는 것 하나가 남았다. 데이터와 마크업 수준은
전부 확인했지만(API 응답 · 목업 모듈 직접 실행 · 타입 · 린트 · 빌드 · 시나리오 6종),
점 색·칸 폭·가로 스크롤이 실제로 읽을 만한지는 화면을 띄워야 안다.

```bash
cd demo/frontend && npm run dev
# http://localhost:5173 → 담당자 탭
#   ?mock=1 과 ?mock=0 을 나란히 열어 컬럼 개수·순서·라벨·점 색이 같은지 본다
```

## 리뷰 후 수정 (커밋 4f9bfec 이후)

자동 품질 검증 에이전트가 진행 없이 멈춰(600초 무응답) 직접 훑었다. 세 건을 고쳤다.

1. **`기타` 칸의 리액트 키 충돌 — 실제 버그.**
   미배정 병합 페이지는 여러 장이 **같은 `slot_key`**(`__unassigned__`)로 온다.
   `key={cell.slot_key}`였으므로 한 칸에 두 장 이상 들어가면 키가 겹쳐 리액트가
   칸을 잘못 재사용한다. `${slot_key}:${document_id}`로 바꿨다.
   (`ApplicationList.tsx`)

2. **P4 테스트의 불변식이 정의보다 느슨했다.**
   "적합 아닌 칸 전부"로 세고 있었는데, 미비 개수의 정의는 **필수** 서류의 미제출만
   센다. 선택 업로드 슬롯이 생기는 날 이 단언이 엉뚱하게 깨진다 — `required`를
   반영하도록 고쳤다. (`run_p4_scenarios.py`)

3. **죽은 분기와 상수 배치.**
   목업의 `?? docs[1]`은 도달 불가(그 시점에 5종이 다 있다)인 데다 "1번이 건보료"라는
   매직 인덱스였다. `if (!target) continue` 가드만 남겼다. 백엔드에서는 `_doc_column`이
   상수 블록 한가운데 끼어 있던 것을 블록 뒤로 옮기고 `FIXED_DOC_COLUMNS`를 줄바꿈했다.

수정 후 재검증: tsc · lint · build 통과, 백엔드 시나리오 6종 전부 통과
(p2 48 / p3 109 / p4 174 / p5 146 / p6 249 / p7 64, 실패 0), 목업 node 실행 불변식 유지.
