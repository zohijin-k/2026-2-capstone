# 기술 설계 — 담당자 목록 서류 컬럼 + 상세 점프

## 1. 설계의 축

**목록 컬럼은 이미 데이터다.** `list.columns` 배열 하나를 헤더와 셀이 같이 읽는다
(`ApplicationList.tsx:Cell` / `api/officer.py:LIST_COLUMNS`). 서류 컬럼은 새 표를 만드는
일이 아니라 **이 배열을 늘리고 행에 대응하는 값을 얹는** 일이다. 컬럼을 하드코딩해서
헤더와 셀이 어긋나는 것이 이 표의 알려진 실패 방식이고, 그 주석이 `Cell` 위에 이미 있다.

**미비 개수와 서류 칸은 한 계산에서 나온다.** 지금 `_missing_count`는 체크리스트를 훑어
개수만 반환하고 버린다. 그 훑는 과정이 곧 서류 칸이다 — 같은 루프에서 둘 다 낸다.
따로 계산하면 "미비 3건인데 칸에는 2개만 빨갛다"가 언젠가 반드시 생긴다.

## 2. 데이터 계약

### 2.1 컬럼 키

서류 컬럼의 키는 `doc:<slot_key>` 로 짓는다. 기존 컬럼 키(`name`, `region`, …)와
같은 이름공간을 쓰므로 접두사로 갈라 놓아야 `Cell`의 `switch`가 섞이지 않는다.

```
doc:resident_abstract       초본
doc:nhis_payment            건보료
doc:nhis_qualification      자격확인
doc:nhis_acquisition_loss   자격득실
doc:work_proof              근로확인서류     ← 사람마다 서류명이 다른 칸
doc:__other__               기타             ← 고정 컬럼에 안 잡히는 나머지
```

앞 4개와 `work_proof`는 `rules/required_docs.py:_double_savings_checklist`가 만드는
고정 슬롯 키 그대로다. 슬롯 키를 컬럼 키로 쓰면 체크리스트가 바뀔 때 컬럼이 저절로
따라오지 않는다는 위험이 있는데, 그래서 **`__other__` 컬럼이 필요하다** — 새로 생긴
슬롯이 조용히 사라지지 않고 `기타`에 나타난다 (R1.4).

### 2.2 행에 붙는 서류 상태

`OfficerRow`에 `documents: OfficerRowDoc[]` 하나를 더한다. 컬럼별 객체(dict)가 아니라
**배열**인 이유는 `기타` 칸에 여러 장이 들어갈 수 있어서다.

```ts
interface OfficerRowDoc {
  /** 어느 서류 컬럼에 들어가는가. 고정 슬롯 키 또는 '__other__'. */
  column: string
  /** 실제 슬롯 키. 미배정 병합 페이지는 '__unassigned__'. */
  slot_key: string
  /** 체크리스트가 정한 이 신청자의 서류명 (툴팁·aria-label 용 전체 이름). */
  label: string
  /** 칸 안에 찍는 짧은 이름. 고정 4칸은 빈 문자열 — 헤더가 이름을 쥔다. */
  short_label: string
  /** 'PASS' | 'NEEDS_REVIEW' | 'FAIL' | null(미제출) */
  status: DocStatus | null
  /** '적합' | '확인필요' | '부적합' | '미제출' */
  status_label: string
  /** 상세에서 열 서류. 미제출이면 null이고 칸은 클릭되지 않는다. */
  document_id: number | null
  required: boolean
}
```

`OfficerList`에는 아무것도 더하지 않는다. 서류 컬럼은 `columns` 배열 안에 이미 들어 있다.

### 2.3 짧은 이름은 어디서 오나

`근로확인서류(4대보험 가입내역 확인서)` 같은 라벨에서 괄호 안을 파싱하지 않는다.
문자열을 되파는 코드는 라벨 문구가 바뀌면 조용히 틀린다. 대신 **`DocType` → 짧은 이름**
표를 `api/officer.py`에 둔다.

```py
DOC_SHORT_BY_TYPE = {
    DocType.INSURANCE_4: "4대보험 가입내역",
    DocType.DAILY_WORK_RECORD: "일용근로내역서",
    DocType.BIZ_REG_PROOF: "사업자등록증명",
    DocType.FARM_BIZ_CERT: "농업경영체 증명서",
    DocType.FISHERY_BIZ_CERT: "어업경영체 증명서",
    DocType.LABOR_CONTRACT: "근로계약서 사본",
    DocType.ADMIN_INFO_CONSENT: "서식5 (자필)",
}
```

`rules/`를 건드리지 않는 선택이다. 짧은 이름은 이 표가 쓰이는 **목록 화면의 사정**이지
서류 규칙이 아니다. `LIST_COLUMNS`의 표기 문구가 이미 같은 파일에 산다.

## 3. 백엔드 변경

### 3.1 `api/common.py` — 페이지 단위 서류 조회

```py
def list_documents_bulk(application_ids: list[int]) -> dict[int, list[Document]]:
    """여러 신청 건의 서류를 한 번에. 목록 한 페이지가 행마다 쿼리하지 않도록."""
```

`_missing_count`가 지금 행마다 `list_documents`를 부른다. 서류 칸까지 행마다 다시 부르면
페이지당 쿼리가 두 배가 된다 (R5.3). `IN` 하나로 읽고 `application_id`로 묶는다.
기존 `list_documents`는 상세 화면이 계속 쓰므로 남긴다.

> 남는 비용: `checklist_for(app)`이 내부에서 `subsidy_selections(app.id)`를 부른다.
> 두배적금은 항상 빈 결과인 쿼리다. 이번 범위에서 건드리지 않고 기록만 남긴다.

### 3.2 `api/officer.py` — 서류 칸 계산

`_missing_count(app)` 를 `_doc_cells(app, documents)` 로 바꾼다. 반환은
`(cells: list[dict], missing: int)` 한 쌍이다 (R1.5).

```
체크리스트의 upload 슬롯을 순서대로 훑으며
  업로드된 것이 있으면  → status = doc.stage1_status, document_id = doc.id
  없으면 required면     → status = None (미제출), missing += 1
  있는데 PASS가 아니면  → missing += 1
  column = slot_key가 DOC_COLUMN_KEYS에 있으면 그 키, 아니면 '__other__'
그리고 어느 슬롯에도 안 붙은 병합 페이지(UNASSIGNED_SLOT)를
  column='__other__' 로 얹고 missing += 1
```

미비 개수의 정의는 지금 그대로다 — **안 올린 필수 서류 + 올렸지만 적합 아닌 서류
+ 미배정 페이지**. 바꾸는 것은 계산이 아니라 "같이 나오는 값"이다.

### 3.3 컬럼 조립

```py
def _columns(program: str | None) -> list[dict[str, str]]:
    """사업에 따라 서류 컬럼을 붙인다.

    취업패키지는 붙이지 않는다 — 항목 회차마다 서류가 늘어(면접비 3회 = 면접확인서
    3장) 고정 컬럼으로 셀 수 없다. 그 사업 목록에서 먼저 보는 것은 '무엇을 신청했나'이고
    그 자리는 `신청 항목` 컬럼이 이미 쥐고 있다.
    """
```

`미비서류` 다음, `접수일시` 앞에 끼워 넣는다.

`_row()`는 **두배적금 행에만** `documents`를 채운다. 사업 필터가 `전체`일 때 같은 표에
섞이는 취업패키지 행은 빈 배열이고, 화면이 `—`로 그린다 (R3.2). 취업패키지 체크리스트
슬롯을 `기타`에 쏟으면 컬럼이 무의미해진다.

> **기록해 둘 기존 불일치(이번에 고치지 않음)**: 백엔드는 사업과 무관하게 항상
> `LIST_COLUMNS`를 준다. 선착순 컬럼셋(`FIRST_COME_COLUMNS`)과 `items_label`,
> `rank_label`은 **목업에만** 있다. 즉 실데이터로 취업패키지를 고르면 지금도 빈
> `점수` 칸이 뜬다. 이번 작업으로 생긴 문제가 아니므로 범위에 넣지 않는다.

## 4. 프론트엔드 변경

### 4.1 `ApplicationList.tsx`

`Cell`의 `switch` **앞**에서 `doc:` 접두사를 먼저 가른다. `default`에 두면
알 수 없는 컬럼을 `-`로 흘리는 기존 안전망과 뒤섞인다.

```tsx
if (column.key.startsWith('doc:')) return <DocCell ... />
```

`DocCell` 한 칸의 규칙:

| 상태 | 표시 | 클릭 |
|---|---|---|
| 제출 · PASS | 초록 점 | O |
| 제출 · NEEDS_REVIEW | 노랑 점 | O |
| 제출 · FAIL | 빨강 점 | O |
| 미제출 | 회색 빈 점 | X |
| 이 사업 아님 (`documents` 비어 있음) | `—` | X |
| `기타`에 여러 장 | 점 여러 개 (각각 클릭) | O |

- 고정 4칸은 점만. 헤더가 서류명을 쥔다 (R1.2).
- `근로확인서류`·`기타` 칸은 점 + `short_label`. 사람마다 다른 칸이라 이름이 있어야 한다 (R1.3).
- 클릭 대상은 `<button>`이다. 점만 있는 칸도 키보드로 닿아야 하고,
  `aria-label`은 "{label} — {status_label}" 전체 문장을 쓴다.
- `onClick`에서 **`e.stopPropagation()`**. 행 전체가 이미 `onClick`으로 상세를 연다.
  이게 빠지면 서류 칸을 눌러도 항상 첫 서류가 열린다 (R2.3).

`Props.onOpen`의 시그니처를 `(applicationId: number, slotKey?: string) => void` 로 넓힌다.

### 4.2 `OfficerConsole.tsx`

`openId: number | null` → `open: { id: number; slot: string | null } | null`.

`<ReviewDetail>`에 `initialSlotKey`를 넘기고 `key`를 `"{id}:{slot}"`로 준다.
같은 신청 건의 다른 서류로 다시 들어올 때 초기 탭 선택이 확실히 다시 돌게 하는 값싼 보험이다.

### 4.3 `ReviewDetail.tsx`

`initialSlotKey?: string | null` 프롭 하나. `load()`의 초기 탭 결정만 바뀐다.

```tsx
setActiveDocId((prev) => prev ?? pickInitialDoc(d, initialSlotKey))
// slot_key가 맞는 서류 → 없으면 첫 서류 (지금 동작)
```

뷰어·탭·하이라이트는 손대지 않는다 (R5.2). 상세는 **탭 방식 그대로**다.

### 4.4 `officer.css`

`.grid__doc` (칸), `.docdot` + `--pass/--review/--fail/--none` (점), `.docdot__name`
(짧은 이름), `.grid__doc-na` (`—`). 컬럼이 6개 늘어 표가 넓어지므로 서류 칸은
`white-space: nowrap`에 좁은 `padding`을 준다. 점 색은 기존 `dotClass`(`format.ts`)와
같은 팔레트를 쓴다 — 상세 탭의 점과 목록의 점이 다른 색이면 안 된다.

## 5. 목업 (`mock-data.ts`) — 이번 작업의 절반

목업은 백엔드가 없을 때 담당자 화면 **전체**를 대신한다. 두배적금 신청건에 서류가
`nhis_payment` 한 장뿐이라, 목업을 손대지 않으면 새 컬럼 5개가 전부 빈 칸으로 뜬다.

### 5.1 근로유형을 사람에게 붙인다

`MockEntry`에 `workCategory` 추가. 분포는 실제에 가깝게 직장가입자가
가장 두껍다 (대략 직장 65 / 지역 15 / 사업자 12 / 농업 6 / 어업 2).
`insuranceType`(`'직장' | '지역'`)이 이미 있으므로 **그 값과 모순되지 않게** 뽑는다 —
건보료 확인서에 "지역가입자"라고 찍혀 있는데 4대보험 가입내역 확인서를 낸 건 말이 안 된다.

### 5.2 서류 5종을 만든다

`makeJobEntry`가 이미 쓰는 패턴을 그대로 따른다 — 서류를 먼저 만들고,
**AI 판정과 미비 개수를 서류에서 역산**한다.

```
resident_abstract      초본            성명·생년월일·주소·전입일·주소변동·병역사항·발급일
nhis_payment           건보료 납부확인서 (지금 있는 것 유지) 가입구분·가구원수·보험료·취업일
nhis_qualification     자격확인서       성명·가구원수·가구원 명단·가입구분
nhis_acquisition_loss  자격득실확인서    성명·사업장명·취득일(=취업일)·상실일
work_proof             근로유형별 1종    유형에 따라 필드가 다름
```

판독값은 그 사람의 사실값에서 나온다 (R4.2). `전입일`은 `transferIn`, `취업일`/`취득일`은
`employedAt`, `가구원수`는 `householdSize`, `보험료`는 `monthlyPremium`을 쓴다.
점수 근거 문장이 이미 이 날짜들에서 역산되므로, 서류가 다른 값을 보이면 심사표와
원본이 어긋난다.

### 5.3 문제를 서류에 배치한다

지금은 신청 건 하나에 `aiStatus`를 먼저 굴리고 사유를 하나 붙인다. 이제 사유가
**어느 서류의 문제인지**가 화면에 보이므로, 사유의 `doc_type`을 슬롯으로 매핑해
그 서류에 `findings`를 얹는다. 매핑표는 `DOC_TYPE_TO_SLOT`로 둔다
(`주민등록초본`·`주민등록등본`→`resident_abstract`, `건강보험료납부확인서`→`nhis_payment`,
`건강보험자격확인서`→`nhis_qualification`).

미제출도 만든다 (R4.4): 대략 12% 확률로 서류 1종을 통째로 빼서
`docs`에서 제외한다. 빠진 서류의 칸이 `미제출`로 떠야 컬럼이 무엇을 위한 것인지 보인다.

그리고 `missing_count`를 역산한다 (R4.3):

```
missing = (체크리스트 종수 − 제출된 종수) + (제출됐지만 PASS 아닌 종수)
aiStatus = FAIL 있으면 FAIL, NEEDS_REVIEW 있으면 NEEDS_REVIEW, 아니면 PASS
```

소득 140% 초과는 지금처럼 곧바로 `FAIL`이고, 그 사유는 `nhis_payment`에 붙는다.

### 5.4 목업도 `documents`를 낸다

`mockOfficerList`가 내는 행에 `documents`를 채운다. 계산은 백엔드 `_doc_cells`와
같은 규칙을 따라야 한다 — **목업이 백엔드와 다르게 보이면 목업의 쓸모가 없다.**
`LIST_COLUMNS`에도 서류 컬럼을 더하고, `FIRST_COME_COLUMNS`는 그대로 둔다.

### 5.5 `mockReviewDetail`은 저절로 좋아진다

상세 좌측 탭이 지금은 두배적금에서 **1개**뿐이다. `docs`가 5장이 되면 탭 5개가 되고,
목록에서 누른 서류로 바로 열리는 R2.1이 목업에서도 성립한다. 별도 작업이 없다.

## 6. 호환성·되돌리기

- `OfficerRow.documents`는 **옵셔널**로 선언한다. 구버전 백엔드 응답(필드 없음)에서
  화면이 터지지 않고 `—`로 그린다. 담당자 화면은 백엔드 실패 시 목업으로 넘어가는
  구조라, 응답 모양이 어긋났을 때 조용히 빈 칸이 되는 편이 낫다.
- 되돌리기 지점: 컬럼 조립(`_columns`)과 `Cell`의 `doc:` 분기만 빼면 나머지 변경
  (`_doc_cells` 리팩터링, 목업 서류 5종, `initialSlotKey`)은 그대로 둬도 화면이 예전과 같다.
- DB 스키마 변경 없음. 마이그레이션 없음.

## 7. 안 하는 것

- 연속 스크롤 뷰어 (사용자가 탭 유지를 선택)
- 취업패키지 목록의 서류 컬럼 (R3.1)
- 백엔드의 `FIRST_COME_COLUMNS` / `items_label` 미구현 보완 (기존 불일치, §3.3 기록)
- 다운로드·저장 경로 (R5.1 금칙)
