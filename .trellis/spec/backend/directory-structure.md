# Directory Structure

> 파이썬 코드 배치. 파이썬은 두 덩어리다 — 판정 엔진 `engine/` 과 데모 백엔드
> `demo/backend/`. 둘은 **단방향**으로만 이어져 있다.

---

## Overview

```
engine/          순수 판정 로직. 외부 의존성 0, 파일 I/O 0, 바깥 참조 0
   ↑ (engine_adapter.py 한 파일이 유일한 접점)
demo/backend/    FastAPI. HTTP · DB · 파일 · 업무 규칙
demo/fixtures/   시연용 더미 서류 생성기 (backend 를 상대 import 한다)
tools/           보조 스크립트 (engine_smoke.py)
```

`engine/` 은 계산만 한다. 여기에 DB·파일·HTTP 가 들어오면 데모 백엔드가 엔진을
자유롭게 호출할 수 없게 되고, 엔진 담당자의 수정이 곧바로 반영되는 지금의 구조가
깨진다. **엔진에서 `demo`/`dashboard`/`docs` 를 참조하지 않는다.**

---

## Directory Layout

```
engine/
├── models.py                 dataclass · Enum (Status, ReasonCode, Applicant, ...)
├── config.py                 심사 기준값. 모듈 최상위 상수 — 런타임에 덮어쓸 수 있다
├── stage1_document_check.py  1단계 서류 적합성
├── stage2_eligibility_check.py  2단계 자격 요건
├── pipeline.py               1·2단계 통합 + 최종 판정 + 담당자 요청 payload
└── reason_messages.py        ReasonCode → 신청자 안내 문구

demo/
├── backend/
│   ├── main.py               FastAPI 앱 + 라우터 등록 + lifespan
│   ├── models.py             SQLModel 5테이블 + get_session + init_db
│   ├── engine_adapter.py     engine/ 와의 유일한 접점 (sys.path · config 덮어쓰기 · 형 변환)
│   ├── reset.py              시연 초기화 (파괴적 — 방어 3겹)
│   ├── api/                  라우터. HTTP 계약만 담당한다
│   ├── rules/                업무 규칙 단일 소스 (배점·서류·자격·역할·사업 상수)
│   ├── ocr/                  판독 3계층 (fixture → pdftext → 상용 API 스텁)
│   ├── forms/                작성 서식 PDF 내보내기
│   └── tests/                run_p{2..8}_scenarios.py — pytest 없이 python -m 실행
└── fixtures/                 더미 서류·템플릿·좌표·기대값
```

---

## Module Organization

**`rules/` 가 업무 규칙의 단일 소스다.** 배점표·서류 목록·자격 기준·역할 정의가
전부 여기 있고, `api/` 와 `forms/` 는 이 값을 읽기만 한다. 라우터 안에
`if program_code == 'job_package'` 같은 분기를 쓰지 않는다 — 사업 차이는
`rules/programs.py` 의 구조체 하나로 표현하고 화면에도 그대로 내려보낸다.

**`api/` 는 HTTP 계약만 담당한다.** 계산이 필요하면 `rules/` 를, 엔진이 필요하면
`engine_adapter` 를 부른다. 라우터끼리 서로를 import 하는 것은 조립 헬퍼를
재사용할 때로 한정한다(예: 현황 라우터가 담당자 라우터의 2쿼리 패턴을 따른다).

**`demo/fixtures/` 는 `demo/backend/` 의 형제로 남아야 한다.** `make_samples.py` 가
`from ..backend.ocr.fixture import FIXTURES` 로 상대 import 하기 때문에, 둘을
다른 패키지로 떼면 곧바로 깨진다.

**경로는 전부 `__file__` 기준**이고 `parents[N]` 으로 깊이를 센다(현재 13곳).
cwd 에 의존하는 코드는 없지만, 폴더를 한 칸만 옮기면 13곳이 동시에 틀어진다.
파일을 옮길 때는 먼저 `parents[` 를 전수 검색한다.

**엔진 설정은 파일을 고치지 않고 런타임에 덮어쓴다.** `engine_adapter.apply_runtime_overrides()`
가 앱 기동 시 1회 `engine/config.py` 의 모듈 전역을 공고문 실제값으로 교체한다.
`stage1`·`stage2` 가 `from . import config` 후 `config.X` 로 **속성 접근**하기 때문에
가능한 방식이다 — `from .config import X` 로 값을 복사하면 이 구조가 깨진다.

---

## Naming Conventions

- 모듈·함수: `snake_case`. 클래스: `PascalCase`. 모듈 상수: `UPPER_SNAKE`.
- 모듈 밖에서 쓰지 않을 것은 `_` 접두사(`_load_entries`, `_scan`). 다른 모듈에서
  `_` 이름을 import 하지 않는다 — 필요하면 공개 이름으로 승격한다.
- 검증 스크립트는 `demo/backend/tests/run_p<단계>_scenarios.py`. `check()` 로 비교하고
  마지막에 `통과 N / 실패 M` 을 찍은 뒤 종료코드로 성패를 알린다. **pytest 를 쓰지
  않는다** — 저장소 전체가 `python -m` + 종료코드 규약으로 일관돼 있다.
- 신규 검증 스크립트를 추가하면 루트 `package.json` 의 `test:api` 에도 넣는다.

---

## Examples

- `demo/backend/api/dashboard.py` — 라우터가 계산을 `rules/` 에 맡기고 매핑과
  가드만 갖는 형태. 구간 역매핑 표를 손으로 베끼지 않고 규칙 표에서 만든다.
- `demo/backend/engine_adapter.py` — 남의 모듈을 수정하지 않고 런타임에 맞추는 방법.
- `demo/backend/reset.py` — 파괴적 스크립트의 방어 구조(마커 · 화이트리스트 · 구조 검사).
- `demo/backend/tests/run_p8_scenarios.py` — "조용히 틀릴 수 있는 것"을 고정하는
  검증 스크립트의 본보기(구간 역순 · 권한 누락 · 집계 크래시).
