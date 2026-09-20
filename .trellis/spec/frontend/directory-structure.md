# Directory Structure

> 프론트엔드 코드 배치. 프론트엔드는 `demo/frontend` **하나뿐**이다 — 신청자·담당자·
> 현황 세 화면이 한 앱의 세 탭이다.

---

## Overview

화면(=탭)이 배치의 1차 기준이다. `src/pages/<화면>/` 안에 그 화면의 컴포넌트·CSS·
전용 유틸을 전부 모으고, **두 개 이상의 화면이 쓰는 것만** `src/` 최상위로 올린다.

이 규칙이 필요한 이유는 CSS가 전역 네임스페이스이기 때문이다. 세 화면이 한 앱에
있는데 "현황 전용 유틸"이 공용처럼 보이면, 다음 사람이 신청자 화면에서 그것을
import 하고 그때부터 두 화면이 서로를 끌고 다닌다.

---

## Directory Layout

```
demo/frontend/src/
├── main.tsx                 진입점. body[data-view] 를 첫 페인트 전에 심는다
├── App.tsx                  3탭 셸 (라우터 없음 — 동시 마운트 + 숨김 전환)
├── api.ts                   백엔드 호출 + 타입
├── index.css                신청자·담당자 공용 규칙(.dstatus 등)
├── app-shell.css            상단 탭 바
├── app/
│   └── initial-params.ts    URL 쿼리를 부팅 시 1회 동결
├── styles/
│   ├── base.css             세 화면이 진짜로 공유하는 것만
│   ├── tokens-form.css      신청자·담당자 토큰  [data-view='apply'|'officer']
│   └── tokens-status.css    현황 토큰 + 다크     [data-view='status']
├── components/              두 화면 이상이 쓰는 UI (Modal, SignaturePad)
├── forms/                   관공서 서식 재현 (서식1·2·3·4·5 + 공통 셸)
├── lib/                     두 화면 이상이 쓰는 순수 유틸 (period, mock-gate)
└── pages/
    ├── applicant/           신청 흐름 6화면 + 각자 CSS
    ├── officer/             담당자 심사 5화면 + officer.css + mock-data.ts
    └── dashboard/           현황 대시보드 — 자족적 하위 트리
        ├── DashboardPage.tsx
        ├── dashboard.css
        ├── components/ charts/ data/ hooks/ lib/ theme.ts
        └── README.md
```

---

## Module Organization

**새 화면을 만들 때**는 `src/pages/<이름>/` 에 컴포넌트·CSS·전용 유틸을 함께 둔다.
`App.tsx` 의 `MODES` 에 탭을 추가하고, 토큰이 기존 두 세트와 다르면
`styles/tokens-<이름>.css` 를 새로 만들어 `body[data-view='<이름>']` 로 스코프를 준다.

**공용으로 올리는 기준은 "두 화면 이상이 쓰는가" 하나다.** 지금 `lib/` 에 있는 것은
`period.ts`(신청자·담당자가 같은 기간 판정을 써야 한다)와 `mock-gate.ts`(담당자·현황이
같은 폴백 규칙을 쓴다)뿐이고, 현황 전용 유틸(`dates` `format` `metrics` `random`)은
`pages/dashboard/lib/` 에 남아 있다.

**`pages/dashboard/` 는 자기 밖으로 나가는 import 가 `app/initial-params.ts` 하나뿐
이다.** 이 자족성이 지연 로드 경계와 디렉터리 경계를 일치시켜 준다 — echarts·지도
경계·목업 생성기가 통째로 별도 청크로 빠진다. 여기서 바깥 모듈을 끌어오기 시작하면
그 경계가 무너지고 초기 번들이 다시 커진다.

**무거운 것은 동적 import 로 격리한다.** 현재 넷: 현황 페이지(echarts),
`officer/DocumentViewer`(pdfjs), `officer/mock-data.ts`, `dashboard/data/generate.ts`.
새로 무거운 의존성을 들일 때는 청크 경계를 먼저 정한다.

---

## Naming Conventions

- 컴포넌트 파일: `PascalCase.tsx`, 유틸·타입: `kebab-case.ts` 또는 `lower.ts`
- import 는 **상대경로 + 확장자 명시**(`'../../api.ts'`). path alias 를 쓰지 않는다 —
  `src/` 밖으로 나가는 import 가 0건이고 최대 깊이가 `../../` 라 alias 가 해결할
  문제가 없다. 도입한다면 부분 도입이 아니라 한 번에 전면 도입한다.
- CSS 클래스는 `블록__요소--상태` (BEM 유사). **접두사 없는 범용 이름을 쓰지 않는다** —
  전역 네임스페이스라 `.grid` `.card` `.badge` 같은 이름은 다른 화면과 충돌한다.
  실제로 담당자 목록 표의 `.grid` 가 현황 대시보드의 12컬럼 컨테이너와 부딪혀
  `.officer-grid` 로 개명했다.
- 디자인 토큰은 `styles/tokens-*.css` 에서만 선언한다. 컴포넌트 CSS 는 `var()` 로
  읽기만 한다.

---

## Examples

- `demo/frontend/src/pages/dashboard/` — 자족적 화면 모듈의 본보기.
  외부 import 1개, 자기 CSS·데이터·차트 설정을 전부 안에 들고 있다.
- `demo/frontend/src/styles/tokens-form.css` — 같은 이름의 변수를 화면별로 다르게
  주는 스코프 분리. 머리말에 `:root` 를 쓰면 안 되는 이유가 적혀 있다.
- `demo/frontend/src/lib/mock-gate.ts` — 공용으로 올리는 기준을 만족한 경우
  (담당자·현황 두 화면이 같은 폴백 규칙을 쓰되 스위치는 각자 갖는다).
