# 설계 — demo · dashboard 통합

## 목표 구조

```
2026-2-capstone/
├── engine/                       ── 이동 없음, 내부 무수정 (C1)
├── demo/
│   ├── backend/
│   │   ├── api/dashboard.py      ★신규
│   │   └── rules/scoring.py      +1줄 (insurance_type)
│   ├── frontend/                 ── 유일한 npm 패키지
│   │   ├── public/favicon.svg    ← dashboard/public/
│   │   └── src/
│   │       ├── App.tsx           3탭 셸
│   │       ├── app/initial-params.ts   ★신규
│   │       ├── styles/           ★신규 base / tokens-form / tokens-status
│   │       ├── api/              ★ api.ts 855줄 → 6분할
│   │       ├── components/ forms/ lib/
│   │       └── pages/
│   │           ├── applicant/    ── 무이동 (C3)
│   │           ├── officer/      ── 무이동, .grid만 개명 (C3)
│   │           └── dashboard/    ★ dashboard/src/ 통째 이식
│   ├── fixtures/                 ── 무이동 (C2)
│   └── docs/
├── docs/                         ── 무이동 (C6)
├── tools/engine_smoke.py         ← demo_run.py
├── package.json                  ★신규 실행 진입점 (workspace 아님)
└── README.md                     폴더 구조 섹션 개정
```

**`apps/`+`services/`+`packages/` 모노레포를 쓰지 않는 이유**: `demo/fixtures/make_samples.py:17`이 `from ..backend.ocr.fixture import FIXTURES`로 백엔드를 상대 import 한다. 두 폴더는 같은 파이썬 패키지의 형제로 남아야 하므로 분리가 성립하지 않는다. 또 이 배치는 `parents[N]` 하드코딩 **13곳을 하나도 건드리지 않는다**.

**`pages/dashboard/`인 이유**: 대시보드 하위 트리는 자기 밖으로 나가는 import가 **0건**이라 통째로 옮기면 내부 상대 import 31건이 전부 살아남는다. `features/`로 개명하는 안도 깊이 보존은 되지만 C3를 위반한다.

---

## 경계 1 — CSS 토큰

### 문제

양쪽 `index.css`가 같은 이름을 다른 값으로 `:root`에 선언한다.

| 변수 | demo | dashboard |
|---|---|---|
| `--surface` | `#fff` | `#fcfcfb` |
| `--text` | `#1a1a1a` | `#0b0b0b` |
| `--muted` | `#666` | `#898781` |
| `--border` | `#ddd` | `rgba(11,11,11,.1)` |
| font-family | 맑은 고딕 | system-ui |
| line-height | 1.6 | 1.5 |

에러 없이 **서식 레이아웃만 조용히 틀어진다.** 클래스 충돌은 전수 조사 결과 `.grid` 하나뿐이다(dashboard 12컬럼 그리드 vs officer 테이블).

### 설계

변수 이름을 **한 글자도 바꾸지 않고** `:root` 선언을 스코프 셀렉터로 강등한다.

```css
/* styles/tokens-form.css */
[data-view='apply'], [data-view='officer'] { --surface:#fff; --text:#1a1a1a; --sheet-w:940px; … }
/* styles/tokens-status.css */
[data-view='status'] { --surface:#fcfcfb; --text:#0b0b0b; … }
[data-theme='dark'] [data-view='status'] { … }
```

CSS 커스텀 프로퍼티는 상속되므로 **선언 위치만 내리면 `var()` 호출부 235곳이 무변경**이다. 접두사 개명(`--form-surface`)은 235곳을 전부 고쳐야 해 비용이 60배다.

**단일 토큰 통일은 기각한다.** demo CSS에 하드코딩 색상이 279개이고 그중 155개가 `officer.css`·`form-sheet.css`에 몰려 있다. `form-sheet.css`는 열 경계값을 시행지침 PDF의 실제 선 좌표에서 뽑은 픽셀 정확 재현물이다. 미적 일관성 때문에 R1.1 회귀 위험을 떠안을 이유가 없다.

**다크모드는 현황 탭에만 존재한다.** 토글 버튼도 현황 탭 헤더 안에 둔다. 관공서 서식은 흰 종이에 검은 선이고 `--form-border:#333`을 반전시키면 더 이상 "서식과 같은 구조"가 아니다. 비대칭을 해소하지 않고 명시적으로 못박는다.

같이 스코프로 내릴 전역 선언: `button,input,select{font:inherit}`, `:focus-visible{outline:2px solid var(--series-1)}`(form 스코프엔 `--series-1`이 없어 outline이 깨진다), `body` background, font-family, line-height. 공통 `base.css`에는 `*{box-sizing:border-box}`만 남긴다.

---

## 경계 2 — 화면 전환

라우터를 도입하지 않고 `useState<Tab>`을 3개로 확장한다.

`demo/frontend/src/App.tsx:4-6`이 "전환할 때마다 언마운트하면 작성하던 내용이 날아간다"는 의도를 명시한다(R1.2). 라우터를 넣어도 이걸 지키려면 셋 다 렌더하고 숨겨야 하므로 **구조가 지금과 같아진다.** 순이익은 URL 하나뿐이고 그건 `history.replaceState` 2줄로 얻는다.

덧붙이는 것 셋:

1. **`src/app/initial-params.ts`** — `?view= date= region= theme= mock= data=`를 부팅 시 1회 읽어 동결. 현재 `?mock`은 `api.ts:777`, `?date/region/theme`는 `dashboard/src/App.tsx:29`에서 **각자 모듈 최상위**에 `window.location.search`를 읽는다. `replaceState`가 끼어들면 읽는 시점에 따라 값이 달라지고, 현황 페이지를 `React.lazy`로 늦게 로드하면 그 모듈은 이미 바뀐 URL을 읽는다.
2. 탭 전환 시 `replaceState`로 `?view=`만 갱신, 나머지 보존(R1.3).
3. **현황 탭만 lazy-mount + `active` prop.** 이유는 0×0 init이 아니다 — `useECharts.ts:26`의 ResizeObserver가 이미 해결한다. 진짜 이유는 ① `dashboard/src/App.tsx:21`의 `generateDataset()`이 모듈 최상위 동기 실행으로 12,821건을 만들어 신청자 첫 페인트를 막고 ② 재생 타이머가 200ms마다 전수 순회를 도는데 다른 탭으로 가도 계속 돈다. `isPlaying = playing && active`로 묶는다.

---

## 경계 3 — 레이아웃

940(신청자) / 1280(담당자) / 1480(대시보드)은 서로 양보할 수 없는 세 계약이다. 셸이 어느 하나를 고르면 나머지 둘이 깨진다.

**셸은 폭을 갖지 않는다.** 탭 바는 full-bleed + `position:sticky`, `body[data-view]`로 문서 최소 폭만 전환한다(`apply`→980, `officer`→1280, `status`→320).

덤으로 기존 버그 2개가 잡힌다. `.shell`이 `width:100%`(뷰포트)인데 담당자는 `min-width:1280px`라 좁은 화면에서 sticky 탭 바가 잘린다 — `body` min-width를 주면 `100%`가 스크롤 폭 기준으로 풀린다. 탭마다 스크롤바 유무가 달라 콘텐츠가 좌우로 흔들리는 건 `html{scrollbar-gutter:stable}` 한 줄로 끝난다.

`--sheet-w:940px`를 `[data-view='apply']` 스코프로 올리고 5개 CSS의 중복 하드코딩을 `var(--sheet-w)`로 교체한다. `officer.css:881`의 `.sheet6 .form-sheet{--sheet-w:100%}`는 요소 직접 선언이라 상속값을 무조건 이기므로 안전하다.

---

## 경계 4 — 데이터 계약

### 서버는 `Dataset`을 준다. 집계는 클라이언트에 남긴다.

`Snapshot`을 서버에서 계산하면 **타임머신이 죽는다.** 재생 버튼이 200ms마다 기준일을 하루씩 미는데(`App.tsx:26,68`) 74일 재생이 74회 HTTP 왕복이 된다. 최적화가 아니라 기능의 존폐다.

포팅 대상도 `metrics.ts` 333줄이 아니라 `lifecycle.ts` + `scoring.ts` + `dates.ts`(로컬 타임존 의존 + 하드코딩 공휴일 3개)까지 실질 500줄 이상이고, 두 벌이 어긋났는지 확인할 테스트가 양쪽에 없다.

응답 크기라는 반대 논거도 여기선 성립하지 않는다 — 실데이터는 현재 **3건(전부 draft), review 0건**이고 시연 후에도 4~5건이다. 12,821건이 네트워크를 타는 경우는 목업인데 **목업은 서버를 거치지 않는다**(아래).

```python
# demo/backend/api/dashboard.py
router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

class DashboardDataset(BaseModel):
    source: Literal["live"]
    total: int                                 # 0이면 클라이언트가 목업으로 전환
    schedule: DashboardSchedule
    regions: list[RegionQuota]                 # 정원표의 정본 (현재 TS/PY 두 벌)
    applications: list[DashboardApplication]   # 공개 12필드
    scores: list[ScoreRow] | None              # 담당자 전용 6필드 — 별도 배열
    scores_withheld_reason: str | None
    notes: list[str]                           # "주소에서 시군을 못 읽은 N건 제외" 등
```

`GET /api/dashboard/dataset?program=&role=` · `GET /api/dashboard/meta?program=` (전건을 받기 전에 배지·폴백을 정하고 싶을 때).

**`/api/officer/dashboard`가 아닌 이유**: 접수 건수·경쟁률·연령 분포는 공개 현황판 성격이고 배점·커트라인만 담당자 전용이다. `/api/officer` 아래 두면 공개 부분까지 담당자 네임스페이스에 갇힌다. 다만 역할 판정은 `rules/roles.py`를 재사용해 권한 모델을 두 벌 만들지 않는다.

### R3 — `scores`를 별도 배열로 두는 것이 핵심

18필드를 유지한 채 6개를 `null`로 채우는 방식은 한 군데만 빼먹어도 조용히 새어나간다. 별도 배열이면 "있거나 없거나"뿐이라 **누락이 구조적으로 불가능**하다(R3.1).

`computeSnapshot`은 `scores` 부재 시 `scoreBins: []` / `totals.cutoff: null` / `regions[].cutoff: {kind:'none'}`으로 떨어진다. `kind:'none'`은 `CutoffTable`·`ScoreDistribution`이 이미 표현할 수 있는 기존 상태다. 민감 필드를 읽는 컴포넌트가 정확히 2개뿐임을 확인했다 — `RegionTable`·`JeonbukMap`·`KpiTiles`·`ReviewStages`는 `cutoff`/`score`를 한 번도 참조하지 않는다.

데모는 로그인이 없다(`OfficerConsole.tsx:6-7` "인증이 아니라 절차 구조를 시연하는 것이 목적"). `?role=province`를 붙이면 누구나 점수를 본다. **권한이 아니라 권한 구조의 시연**임을 `scores_withheld_reason`과 화면에 명시한다(R3.2).

### 하이브리드 = 배타적 토글

| `?data=` | 동작 |
|---|---|
| `mock` | 강제 목업 |
| `live` | 강제 실데이터 (0건이면 빈 화면 그대로 — 검증용) |
| 없음 | 자동: `/dataset` 호출 → 실패 또는 `total==0`이면 목업 |

**건수 임계값을 두지 않는다.** 시연 도중 기준을 넘는 순간 화면이 통째로 갈아엎어진다. 기존 `api.ts`의 규칙도 **0건이냐 아니냐** 하나뿐이다.

**merge를 버리는 이유**: ① 전주시 목업 5,828건에 실제 1건을 더하면 12,821→12,822이라 R2.4의 "숫자가 1 오른다"가 **화면에서 안 보인다** — merge는 목적한 효과를 못 낸다. ② 실제 `submitted_at`을 목업 타임라인으로 옮겨 앉히는 건 기록의 위조다. ③ 실제 1건의 커트라인이 가짜 경쟁자 5,827명 기준으로 계산되어 담당자용 패널이 오염된다.

타임라인 불일치(목업 3/3~5/15 vs 실데이터 오늘)는 `schedule`을 모드별로 만들어 해결한다. live는 `openAt`=최초 `submitted_at`의 00:00, `closeAt`=오늘 23:59. `FilterBar`가 슬라이더 범위를 schedule에서 끌어내므로 화면 코드를 안 건드린다. **대가는 정직하게 적는다 — live 모드에서 타임머신은 사실상 하루짜리가 된다.** 타임머신은 목업 모드의 기능이고 live 모드의 기능은 R2.4다.

**목업 생성기는 클라이언트에 남긴다.** 폴백의 정의상 서버에 두면 안 된다 — "백엔드가 죽었을 때 목업으로 떨어진다"가 폴백인데 목업이 서버에 있으면 폴백도 같이 죽는다. `mock-data.ts`가 클라이언트에 있는 이유와 같다.

### 필드 매핑의 위험 구간

| 필드 | 출처 | 주의 |
|---|---|---|
| `incomeBand` | `review.score_json` income 점수 | **인덱스 아닌 점수값 역매핑.** TS `[0]`=100%미만/40점 vs PY `[0]`=(130.0, 28) — 정확히 역순이라 인덱스로 주고받으면 점수가 뒤집힌다 |
| `residenceBand`/`workBand` | 동 residence/work 점수 | 순서·점수 완전 일치 — 직접 매핑 가능 |
| `age` | `form1_json.birth` | TS `AGE_BANDS[3]={min:35,max:39}` vs PY `(200,…)` 상한 없음. 40세면 `ageBandIndex`→`-1`→`AGE_BANDS[-1].points` **TypeError** |
| `region` | `form1_json.address` → `extract_region()` | 빈 문자열 반환 가능 → 행 제외 + `notes` 기록 |
| `workType` | `form1.workType`(4종) + `doc_context.work_category`(5종) | 대시보드 5종과 **세 축이 안 맞는다.** `'기타(혼합)'`은 대응 없음 |
| `insuranceType` | — | `form1`에 필드가 없다. 채점기가 값을 들고 있으나 `ScoreSheet.as_dict()`가 안 내보낸다 → 1줄 추가로 해소 |
| `firstSelected`/`finalSelected` | `officer_decision` + `officer_role` | `review`에 결정 컬럼이 1개뿐이라 시군 승인 → 도 승인 시 앞 기록이 덮어써진다 |

### 크래시 가드는 서버 매핑 계층에 둔다

`computeSnapshot`은 목업 생성기가 만든 값만 본다는 전제라 방어 코드가 없다. 실데이터를 그대로 흘리면 터진다.

| 조건 | 터지는 곳 | 서버가 할 것 |
|---|---|---|
| region이 14시군 밖 | `metrics.ts:180` `accumulators.get()!` | 행 제외 + `notes` |
| `score < 66` | `metrics.ts:271` `scoreBins[score-66]` | `scores`에서 제외 |
| age 18~39 밖 | `scoring.ts:53` `AGE_BANDS[-1]` | clamp 또는 제외 |
| `householdSize == 0` | `metrics.ts:269` 조용한 누락 | 최소 1 보장 |

클라이언트에 두면 목업 경로에 불필요한 분기가 생기고 "로직 중복 0" 전제가 깨진다.

### R2.5 — 실데이터로 만들 수 없는 지표

| 지표 | 이유 |
|---|---|
| 심사 진행률 · 평균 처리기간 · '서류확인 대기' | 엔진 1·2단계가 `POST /submit` 안에서 동시에 끝난다. 제출과 판정 사이에 시간축이 없다 |
| 일별 접수 추이 | 실데이터 제출이 시연 당일 하루에 몰린다 → 막대 1개 |
| 커트라인 | 전주시 정원 550 vs 접수 3건 → 전 시군 `undersubscribed` |
| 1차(120%) ↔ 최종(100%) 동시 표시 | `review.officer_decision` 1컬럼뿐이라 앞 기록이 덮어써진다 |
| `rejectStage='duplicate'` | 행복e음·일모아 미연동(C3)이라 발화 경로가 없다 |
| 시군별 비교 · 지도 | 대본상 제출이 전부 전주시 → 13개 시군 회색 |
| 부적합 사유 목업↔실데이터 비교 | 목업 문자열 13종과 엔진 `ReasonCode` 메시지가 한 건도 안 겹친다 |

`insuranceType`만 `ScoreSheet.as_dict()` 1줄로 해소된다. 나머지는 원천이 없으므로 화면에 "해당 없음" 상태를 준다.

---

## 경계 5 — `api.ts` 분할과 번들

### 목업 게이트를 인스턴스로

`api.ts:781`의 `let mockActive`는 모듈 전역 단일 값이다. 현황 탭이 폴백으로 이걸 켜면 `api.ts:798`에서 **담당자 탭까지 목업으로 끌려간다.** 한 번 켜지면 새로고침 전까지 안 꺼진다. `createMockGate()` 인스턴스 2개로 분리하고 각자 자기 배너만 제어한다.

재사용하는 것은 패턴이다 — `?mock=1|0` 문법(시연 중 손에 익은 동작), `catch` + "0건이면 트립" 2조건, **목업임을 숨기지 않는 규약**.

### 6분할

`api/http.ts`(~40) · `api/types.ts`(~370) · `api/applicant.ts`(~180) · `api/officer.ts`(~140) · `api/dashboard.ts`(~80 신규) · `api/mock-gate.ts`(~40).

### 번들 (기준선: demo 791KB + dashboard 915KB → 단순 병합 ~1.7MB)

| # | 대상 | 크기 | 방식 |
|---|---|---|---|
| 1 | `pages/officer/mock-data.ts` | 105,751 B | 동적 import. `api.ts:3-9`가 정적 import 하고 13개 페이지가 api.ts를 쓴다 → **신청자가 첫 화면을 여는 순간 담당자 목업을 받는다(지금도 그렇다).** 호출부 5개가 전부 이미 Promise 반환이라 공개 시그니처 무변경으로 전환 가능 |
| 2 | 현황 페이지 | echarts ~760KB + geo 14KB | `React.lazy` — lazy-mount와 동일 경계 |
| 3 | `DocumentViewer` | pdfjs ~435KB | `React.lazy` (워커 1.2MB는 `?url` 덕에 이미 분리) |
| 4 | `data/generate.ts` | — | 폴백 결정 후에만 로드 |

`manualChunks`는 쓰지 않는다 — 동적 import가 이미 자연스러운 분할선이다. 목표 초기 청크 250~300KB(A2).

---

## 롤아웃 / 롤백

단계마다 **브랜치 1개 = 커밋 2개**(`mv:` 순수 이동 / `fix:` 순수 수정). 시작 전 `git tag pre-stageN`, 되돌리기는 push 전이면 `git reset --hard pre-stageN`.

커밋을 분리하는 실익은 **리뷰**다. git의 rename 추적은 커밋 경계가 아니라 내용 유사도 기반이라 섞어도 대개 추적되지만, `git show --stat`의 첫 커밋이 순수 rename 목록이면 팀원이 10초에 확인하고 끝낸다.

**push 단위로는 분리하지 않는다.** 이동만 push 된 main은 빌드 불가(echarts 미설치, 고아 CSS)라 팀 전원이 멈춘다.

### 팀 협업

현재 미병합 브랜치 0개, `origin/main...main` = 0/0, 트리 clean. 이 창은 지빈이나 진이 새 브랜치를 파는 순간 닫힌다.

착수 전 공지의 핵심 문장: **"`demo/backend/`와 `engine/` 파일은 1개도 옮기지 않습니다."** 실제 이동 대상은 `dashboard/`(본인 것)와 루트 파일 2개뿐이라 충돌 표면이 거의 없다는 사실을 먼저 알려야 팀이 불필요하게 멈추지 않는다.
