# 실행 계획 — demo · dashboard 통합

명령은 전부 **저장소 루트**에서. `python -X utf8`이 `PYTHONIOENCODING=utf-8 PYTHONUTF8=1`과 동치이고 PowerShell·cmd·npm script에서 동일하게 동작한다(환경변수 prefix는 PowerShell에서 문법 오류다).

단계마다 시작 전 `git tag pre-stageN`. 되돌리기는 push 전이면 `git reset --hard pre-stageN`.

---

## Stage 0 — 기준선 ✅ 완료 (2026-09-20)

- [x] `python -X utf8 -m demo.fixtures.make_samples` → 25개 PDF 생성
- [x] 검증 스크립트 6종 → **790 통과 / 0 실패** (p2 48 · p3 109 · p4 174 · p5 146 · p6 249 · p7 64)
- [x] 두 프론트 build + oxlint → exit 0. 메인 청크 demo 791,022 B / dashboard 915,130 B
- [x] `python demo_run.py` → exit 0

`demo/fixtures/samples/`가 없으면 p3·p5·p6이 이동과 무관하게 실패하므로 이 단계를 건너뛰면 이후 원인 판별이 불가능하다.

---

## Stage 1 — 충돌 선(先)제거 (이동 0)

이동 전에 해야 Stage 2의 이동 커밋이 순수해진다.

- [ ] `.grid` → `.officer-grid` — `demo/frontend/src/pages/officer/officer.css` 5개 룰(308·314·315·322·327·331행 부근) + `ApplicationList.tsx:379` 1곳. `.grid__missing`(156행)과 `.grid-scroll`(418행)은 **다른 클래스이므로 건드리지 않는다**
- [ ] `demo/backend/tests/run_p4_scenarios.py:645-648`의 `_scan()`에 존재 확인 3줄 — `if not root.is_dir(): raise FileNotFoundError(...)`. `Path.rglob()`은 없는 폴더에 예외 없이 `[]`를 돌려주므로, 스캔 경로가 틀어지면 "담당자는 파일을 내려받지 않는다"는 유일한 정적 게이트가 **아무것도 검사하지 않고 초록으로 통과한다**

**게이트**
```powershell
python -X utf8 -m demo.backend.tests.run_p4_scenarios     # 174 통과
npm --prefix demo/frontend run build
```
육안: 담당자 접수목록 표가 정상인가.

**롤백**: `git reset --hard pre-stage1` (이동이 없어 충돌 여지 없음)

---

## Stage 2 — 대시보드 흡수 (최대 단계)

### 2a `mv:` 순수 이동

- [ ] `git mv dashboard/src/{charts,components,data,hooks,lib}` → `demo/frontend/src/pages/dashboard/`
- [ ] `git mv dashboard/src/theme.ts` → 동 위치
- [ ] `git mv dashboard/src/App.tsx` → `pages/dashboard/DashboardPage.tsx`
- [ ] `git mv dashboard/src/index.css` → `pages/dashboard/dashboard.css` (`src/index.css`와의 혼동 제거)
- [ ] `git mv dashboard/README.md` → `pages/dashboard/README.md`
- [ ] `git mv dashboard/public/favicon.svg` → `demo/frontend/public/favicon.svg`
- [ ] `git rm` 10개 — `main.tsx` `index.html` `package.json` `package-lock.json` `tsconfig{,.app,.node}.json` `vite.config.ts` `.oxlintrc.json` `.gitignore`. **`tsconfig.app.json`·`.oxlintrc.json`은 양쪽이 바이트 단위로 동일**하고 `package.json`은 의존성 1개씩만 다르다
- [ ] `dashboard/node_modules/`는 untracked라 이동하지 않는다 — 팀원에게 수동 삭제 안내

**게이트**: `git show --stat HEAD`가 전 항목을 rename/delete로만 보여야 한다.

### 2b `fix:` 내용 수정

- [ ] `demo/frontend/package.json`에 `echarts ^6.1.0` 추가 → `npm --prefix demo/frontend install`로 lock 재생성
- [ ] `src/styles/{base,tokens-form,tokens-status}.css` 신규 — `:root` → `[data-view]` 스코프 강등 (design 경계 1). 전역 선언 6종도 같이 내린다
- [ ] `dashboard.css`의 `:root` / `:root[data-theme='dark']` 블록 제거 → 나머지 ~660줄은 그대로
- [ ] `--sheet-w:940px`를 `[data-view='apply']`로 올리고 5개 CSS의 중복 하드코딩 교체 — `apply-flow` `program-picker` `my-page` `final-check` `subsidy-items`
- [ ] `html{scrollbar-gutter:stable}` + `body[data-view]` min-width 3종 (design 경계 3)
- [ ] `src/app/initial-params.ts` 신규 — 쿼리 6종 1회 동결
- [ ] `src/App.tsx` 3탭 셸 — `replaceState`로 `?view=` 동기화, 현황 탭만 lazy-mount + `active` prop
- [ ] `DashboardPage.tsx` — `active` prop 수용, `isPlaying = playing && active`, `dataset`을 모듈 상수에서 주입식으로
- [ ] `src/api/` 6분할 + `createMockGate()` 인스턴스 2개 (design 경계 5). import처 13개 파일 수정
- [ ] 번들 분할 4곳 — `mock-data.ts` 동적 import, 현황 페이지·`DocumentViewer` `React.lazy`, `generate.ts` 동적 import

**게이트**
```powershell
npm --prefix demo/frontend install
npm --prefix demo/frontend run build          # 메인 청크 500KB 미만인지 확인 (A2)
npx --prefix demo/frontend oxlint demo/frontend/src
python -X utf8 -m demo.backend.tests.run_p4_scenarios   # 스캔 범위에 대시보드가 새로 편입됨
python -X utf8 -m demo.backend.tests.run_p6_scenarios
git log --follow --oneline -- demo/frontend/src/pages/dashboard/components/KpiTiles.tsx
```

**육안 검증을 반드시 포함한다.** `tsc`·`oxlint`·`vite build`는 CSS 충돌을 **전혀 잡지 못한다.** 순서: ① 담당자 접수목록(`.grid`) ② 신청자 서식1(940px·맑은고딕·행간 1.6) ③ 현황 탭 차트 6개 ④ 다크모드가 현황 탭에만 적용 ⑤ **현황 탭 먼저 → 담당자 탭에 실데이터**(게이트 오염 회귀).

> **2a만 push 하지 않는다.** 2a 상태의 main은 빌드 불가라 팀 전원이 멈춘다. 배선이 길어질 조짐이면 **쪼갠다**: (2-1) 이동 + echarts 추가 + CSS 스코프화까지 — 배선 없이도 빌드가 초록이다(하위 트리가 자족적이라 타입체크를 통과하고 트리셰이킹으로 번들에서 빠진다). (2-2) 탭 배선은 별도 브랜치.

**롤백**: `git reset --hard pre-stage2` 후 `npm --prefix demo/frontend install` 재실행(lock이 바뀌었으므로)

---

## Stage 3 — 백엔드 연동

- [ ] `demo/backend/rules/scoring.py` — `ScoreSheet.as_dict()`에 `insurance_type` 1줄. 채점기가 값을 이미 들고 있는데 안 내보내서 지금은 `basis` 문장 안에만 박혀 있다
- [ ] `demo/backend/api/dashboard.py` 신규 — Pydantic 모델 4종 + 매핑 계층 + `GET /dataset`, `GET /meta`
  - 쿼리 2개 고정: `officer.py`의 `_load_entries` 2쿼리 패턴 재사용, N+1 없음
  - `document` 테이블은 조회하지 않는다 — 부적합 사유는 `review.review_payload_json`에 이미 복사돼 있다
  - **크래시 가드 4종**(region 제외 / score<66 제외 / age clamp / householdSize≥1)을 여기 둔다
  - **`incomeBand`는 인덱스가 아니라 점수값으로 역매핑**(40→0 … 28→4). 인덱스로 주고받으면 점수가 정확히 뒤집힌다
  - `scores`를 별도 배열로. 권한 없으면 `None` + `scores_withheld_reason`
- [ ] `demo/backend/main.py` — `include_router(dashboard.router)`
- [ ] `demo/frontend/src/api/dashboard.ts` — `?data=` 3분기 + 0건/실패 시 폴백
- [ ] `DashboardPage.tsx` — 배지(`badge-mock` / `badge-live` 신규) + 푸터 문구 모드 분기. 왜 그 모드인지 `title`로 붙인다
- [ ] `metrics.ts` — `scores` 부재 시 `scoreBins: []` / `cutoff: null` 분기 (한 곳)
- [ ] `types.ts` — `Application` 18필드에서 배점 6필드 분리 → `ScoreRow`, `Dataset`에 `scores?`/`source` 추가
- [ ] 산출 불가 지표 7종(design R2.5 표)에 "해당 없음" 상태 부여

**게이트**
```powershell
npm run dev:api
curl http://localhost:8000/api/dashboard/meta
curl http://localhost:8000/api/dashboard/dataset      # scores 필드가 없는지 확인 (A6)
curl "http://localhost:8000/api/dashboard/dataset?role=province"   # scores 있음
```
육안: 신청자 탭에서 1건 제출 → 현황 탭(`?data=live`) 숫자 증가 (A5-⑥).

**롤백**: `git reset --hard pre-stage3`

---

## Stage 4 — 루트 진입점

- [ ] 루트 `package.json` 신규 — **`workspaces` 키 없음, `dependencies` 없음.** `cd` 대신 `--prefix`를 써서 셸 무관하게
  ```jsonc
  "setup":   "npm run setup:api && npm run setup:web && npm run setup:fixtures",
  "dev:api": "uvicorn demo.backend.main:app --reload --port 8000",
  "dev:web": "npm run dev --prefix demo/frontend",
  "test":    "npm run test:api && npm run build",
  "reset":   "python -X utf8 -m demo.backend.reset"
  ```
- [ ] `git mv demo_run.py tools/engine_smoke.py` + `tools/__init__.py`. **조용히 깨진다** — 지금 동작하는 이유는 `sys.path[0]`이 스크립트 폴더(=루트)이기 때문이고, `tools/`로 내려가면 `from engine.models import`가 `ImportError`다
- [ ] `engine_smoke.py`에 **assert 8개 + `raise SystemExit(1 if failed else 0)`** (약 30줄). 시나리오를 늘리지 않고 `result.status` 1개만 검사한다 — 세부까지 고정하면 진이 사유 코드를 다듬을 때마다 깨져서 무시당한다
- [ ] `.gitignore` — `dashboard/` 소멸 반영, 낡은 주석 갱신. **`!demo/fixtures/templates/*.pdf`는 손대지 않는다** (전역 `*.pdf`에서 커밋 대상 PDF 2개를 구해내는 유일한 장치)
- [ ] `demo/backend/reset.py:43` `REPO_MARKERS`에서 죽은 `"dashboard"` 항목 정리

**게이트**
```powershell
npm run build ; npm run lint ; npm run test:api ; npm run test:engine
npm run reset -- --dry-run
git check-ignore -v demo/fixtures/templates/서식1.pdf   # "무시 안 함"이어야 한다
```
일부러 실패를 만들어 `engine_smoke`의 종료코드가 1인지 한 번 확인한다.

**롤백**: `git reset --hard pre-stage4`

---

## Stage 5 — 문서

- [ ] 루트 `README.md` 33~42행 교체 — 폴더 구조 + "빠른 시작"(`npm run setup` → `dev:api` → `dev:web`). `docs/demo-site-dev-plan.md`가 3개 영역 공유 도메인 출처임을 한 줄로 밝힌다
- [ ] `demo/README.md` — 설치 절차를 루트 링크로 축약, 명령 12곳을 `python -X utf8`로 교체, 폴더 트리에 `src/pages/dashboard/` 반영
- [ ] `demo/docs/demo-script.md` 준비 체크리스트 명령 갱신
- [ ] `.trellis/spec/{backend,frontend}/directory-structure.md` 2개만 (각 30~40줄) — Trellis가 코드 작성 전에 주입하는 파일이라 재편 직후 첫 작업자가 옛 구조로 되돌리는 것을 막는 유일한 장치다. 나머지 11개는 별도 태스크

**게이트**
```powershell
Select-String -Path README.md,demo/README.md,demo/docs/*.md -Pattern "dashboard/|demo_run\.py|PYTHONIOENCODING"
#   → 히트 0건 (docs/demo-site-dev-plan.md는 과거 계획 문서라 제외)
```
README의 명령을 위에서부터 그대로 복붙해 기동되는지 확인 (A8).

**롤백**: `git reset --hard pre-stage5`

---

## 최종 판정 (prd A1~A8)

```powershell
npm run setup
npm run test        # p2~p7 790 통과 / 0 실패 — Stage 0과 동일해야 한다
npm run test:engine
npm run dev:api ; npm run dev:web
```

육안 6종(A5) + 응답 본문에 배점 필드 부재 확인(A6) + `git log --follow`(A7).

## 자식 태스크 분리

Stage 2와 Stage 3은 검증 단위가 독립적이므로 자식 태스크로 쪼갠다. Stage 1·4·5는 분량이 작아 부모에 둔다.
