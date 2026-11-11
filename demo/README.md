# 데모 사이트 — 전북청년 두배적금 · 취업지원패키지 신청서류 자동 검토 시스템

신청자가 공고문 서식을 원본 PDF 위에서 온라인으로 작성·서명하고, 담당자가 원본 서류를
화면에서 확인하며 심사하는 데모다. 두배적금 서식5는 스캔본 제출도 선택할 수
있다. 사업 2종(두배적금 · 취업지원패키지)을 같은 파이프라인으로 처리한다.

- 요구사항: `.trellis/tasks/09-16-demo-site/prd.md`
- 설계: `.trellis/tasks/09-16-demo-site/design.md`
- 업무 규칙 원문(자격요건·제출서류·심사표 배점·중위소득 기준표): `docs/demo-site-dev-plan.md`
- **시연 대본**: [`docs/demo-script.md`](docs/demo-script.md)
- **담당자 화면 목업 데이터**: [`docs/officer-mock-data.md`](docs/officer-mock-data.md)

> ⚠️ **PC 전용**이다. 서식 원형을 지키기 위해 폭 940px 고정 레이아웃을 쓴다(R8.6).
> 좁은 화면에서는 셀을 재배치하지 않고 가로 스크롤만 생긴다.

> ⚠️ **더미 데이터만 쓴다.** 이름·주민등록번호·주소·계좌번호는 전부 가짜이고,
> 실물 서류는 저장소에 두지 않는다(R7.1). 업로드 원본과 SQLite 파일은 커밋되지
> 않는다(루트 `.gitignore`).

---

## 1. 폴더

```
demo/
├── backend/            FastAPI — 신청·업로드·심사·담당자 API
│   ├── main.py         엔트리 (uvicorn 대상)
│   ├── reset.py        시연 초기화 (파괴적)
│   ├── engine_adapter.py   engine/ 와의 유일한 접점
│   ├── api/ ocr/ rules/    라우터 · 판독 3계층 · 업무 규칙
│   ├── forms/          원본 PDF 위 입력·서명 렌더링 및 서식 응답
│   └── tests/          P2\~P15 시나리오 검증 스크립트 (pytest 없이 실행)
├── frontend/           React + Vite (신청자 화면 · 담당자 화면)
├── fixtures/
│   ├── make_samples.py 시연용 더미 서류 생성기
│   ├── cut_templates.py     원본 공고 PDF에서 서식별 A4 쪽 템플릿 생성
│   ├── build_form_coords.py 템플릿 → 서식 좌표 맵 추출
│   ├── samples/        생성된 더미 PDF (gitignore)
│   ├── templates/      두 사업 신청자 서식 PDF 템플릿 (커밋 대상)
│   ├── form_coords/    서식별 필드 좌표 맵 JSON
│   └── expected/       시연 시나리오 10종의 기대 결과 JSON
├── docs/demo-script.md 시연 대본
├── docs/officer-mock-data.md 담당자 화면 목업 데이터 (+ 대안 2종)
├── storage/            업로드 원본 (gitignore)
└── demo.db             SQLite (gitignore)
```

`engine/`은 **복사하지 않는다.** `engine_adapter.py`가 저장소 루트를 `sys.path`에
올려 `from engine.pipeline import run_pipeline` 으로 직접 import 한다. 엔진 담당자의
수정이 그대로 반영되어야 하기 때문이다.

---

## 2. 준비 (최초 1회)

검증에 쓴 환경: **Python 3.14.0 · Node 22.19.0** (Windows 11).
Python은 3.12 이상, Node는 20 이상이면 된다.

```bash
# 저장소 루트에서
pip install -r demo/backend/requirements.txt

cd demo/frontend
npm install
```

시연용 더미 서류를 만든다. `demo/fixtures/samples/`에 25개 PDF가 생긴다.

```bash
# 저장소 루트에서
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -m demo.fixtures.make_samples
```

> Windows 콘솔은 기본 인코딩이 cp949라 한글 출력이 깨진다. 파이썬 스크립트를
> 돌릴 때는 `PYTHONIOENCODING=utf-8 PYTHONUTF8=1`을 앞에 붙인다.

---

## 3. 기동

터미널 2개가 필요하다. **백엔드는 반드시 저장소 루트에서** 띄운다 — 그래야
`engine/` 을 import 할 수 있다.

```bash
# 터미널 1 — 백엔드 (저장소 루트에서, .env의 전북AI 설정을 함께 넘긴다)
uvicorn demo.backend.main:app --reload --port 8000 --env-file .env
```

`.env`가 없거나 `JBAI_API_KEY`·`JBAI_ALLOW_REAL_DOCS=true` 중 하나라도 빠지면 전북AI 없이
로컬 OCR부터 동작한다. 변수 설명은 저장소 루트의 `.env.example`에 있다.

```bash
# 터미널 2 — 프론트엔드
cd demo/frontend
npm run dev
```

브라우저에서 <http://localhost:5173> 을 연다. 상단 탭으로 **신청자 / 담당자** 화면을
오간다. Vite가 `/api` 요청을 8000 포트로 프록시하므로 별도 설정은 없다.

접수된 신청 건이 하나도 없으면 담당자 화면은 **목업 데이터**로 채워진다(상단에 노란
배너가 뜬다). `?mock=1`로 강제로 켜고 `?mock=0`으로 끈다 —
[`docs/officer-mock-data.md`](docs/officer-mock-data.md).

확인용 엔드포인트:

```bash
curl http://localhost:8000/api/health     # {"status":"ok"}
curl http://localhost:8000/api/programs   # 사업 2종 설정
```

API 문서는 <http://localhost:8000/docs> (FastAPI 자동 생성).

신청자 흐름은 **본인인증 → 서식 작성 → 서류 업로드 → 확인 및 제출**이다. 서식 화면은
공고문 원본 PDF 위에서 온라인 작성·서명하며, 마이페이지는 상단 신청번호 옆 버튼으로
언제든 연다. 서식 목록 위의 **다운로드** 메뉴에서는 작성한 서식 PDF 한 파일과 원본 HWP를
받을 수 있다. 담당자 화면은 업로드 원본을 브라우저 안에서만 보고, 원본 파일 저장 기능은
제공하지 않는다.

---

## 4. 시연 초기화

**시연 직전에 반드시 한 번 돌린다.** 이전 시연에서 만든 신청 건이 담당자 목록에
남아 있으면 화면이 달라진다.

```bash
# 무엇을 지울지 보기만 한다
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -m demo.backend.reset --dry-run

# 확인을 묻고 지운다
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -m demo.backend.reset

# 확인 없이 지운다 (시연 직전)
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -m demo.backend.reset --yes
```

지우는 것은 `demo/demo.db`와 `demo/storage/` **둘뿐**이다. 소스·시연 샘플·문서는
건드리지 않고, git이 추적하는 파일은 하나도 지워지지 않는다.

> **Windows에서는 uvicorn을 먼저 멈춰야 한다.** 실행 중이면 SQLite 파일이 잠겨
> 삭제가 실패한다. 그 경우 안내 문구와 함께 종료코드 3으로 끝난다.

빈 DB는 서버를 다음에 띄울 때 자동으로 만들어진다.

---

## 5. 검증 스크립트

pytest 없이 그대로 실행된다. 전부 임시 폴더에서 돌기 때문에 `demo/demo.db`·
`demo/storage/`(시연용 데이터)를 건드리지 않는다.
`demo/fixtures/samples/`가 없으면 첫 시나리오 실행 시 `make_samples`가 더미 PDF를 자동 생성한다.

```bash
# 저장소 루트에서
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -m demo.backend.tests.run_p2_scenarios  # 업로드 즉시 판정
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -m demo.backend.tests.run_p3_scenarios  # 통합심사·채점
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -m demo.backend.tests.run_p4_scenarios  # 담당자 원본 서류 인라인·저장 경로 검사
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -m demo.backend.tests.run_p5_scenarios  # 취업지원패키지 분기
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -m demo.backend.tests.run_p6_scenarios  # 리셋 후 시연 10종 재현
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -m demo.backend.tests.run_p7_scenarios  # 작성 서식 PDF 내보내기
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -m demo.backend.tests.run_p8_localocr_scenarios
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -m demo.backend.tests.run_p9_identity_scenarios
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -m demo.backend.tests.run_p11_criteria_scenarios
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -m demo.backend.tests.run_p12_subsidy_criteria_scenarios
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -m demo.backend.tests.run_p13_household_scenarios
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -m demo.backend.tests.run_p14_pdf_forms_scenarios
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -m demo.backend.tests.run_p15_jbai_scenarios
```

실패한 시나리오 뒤에도 나머지를 끝까지 실행하려면 아래 반복문을 쓴다. 파일 이름 순서상 P11\~P15가 P2\~P9보다 먼저라, 첫 실패에서 멈추면 뒤 시나리오 결과를 확인할 수 없다.

```bash
for f in demo/backend/tests/run_p*_scenarios.py; do echo "== $f"; python -m demo.backend.tests.$(basename "$f" .py) || echo "FAILED $f"; done
```

`run_p6_scenarios`는 **리셋 → S1\~S10 연속 실행 → 기대값 대조**를 두 번 반복해,
리셋이 실제로 동작하고 두 번째 시연에서도 같은 화면이 나오는지(신청번호까지)
확인한다. 기대값은 `fixtures/expected/S*.json`에 있다.

`--live`를 주면 임시 폴더가 아니라 **진짜 `demo/`를 리셋하고** 거기서 돌린다.
시연 직전 최종 점검용이며, 끝나면 다시 리셋된 상태로 정리된다.

```bash
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -m demo.backend.tests.run_p6_scenarios --live
```

프론트엔드 점검:

```bash
cd demo/frontend
npx tsc -b && npx oxlint && npx vite build
```

---

## 6. 신청 서식 온라인 작성·보관

두배적금 서식1\~5와 취업지원패키지 신청서·동의서는 신청자가 원본 서식 PDF 위에서
온라인으로 작성하고 서명한다. 회사가 작성하는 면접확인서도 같은 템플릿을 사용해
화면에서 확인·인쇄할 수 있다. 화면 작성과 미리보기는 같은 서식 렌더링을 쓴다.

서식 목록 위의 **다운로드** 메뉴에서 작성이 완료된 서식을 번호순으로 합친 PDF 한 파일과
원본 HWP를 제공한다. 작성 PDF는 본인 보관용이고, 신청자 본인만 받을 수 있다. 제출 시
작성값·서명·작성일을 고정하므로 제출 뒤에도 같은 서식 파일이 제공된다. 담당자 화면에는
작성 서식과 업로드 원본을 브라우저 안에서 보여 주며, 원본 서류를 저장하는 경로는 없다.

두배적금 서식5는 작성 방식을 온라인 작성과 스캔본 제출 중 고를 수 있다.
스캔본 제출을 선택하면 상단 다운로드 메뉴에서 서식을 받을 수 있고, 서류 업로드 단계에
「서식5 행정정보 공동이용 사전동의서(스캔본)」 칸이 필수로 추가된다. 업로드한 스캔본은 본문 제목으로 종류를
판별하고, 성명·생년월일·동의 여부·서명 잉크를 확인한다. 손글씨 항목을 판독하지 못하면
자동 부적합 대신 담당자 확인으로 보낸다.

템플릿과 좌표 맵은 **원본 공고 PDF의 서식 쪽**에서 생성한다. 원본이 개정되면 저장소 루트에
원본 PDF를 준비하고 다음 명령을 실행한다.

```bash
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -m demo.fixtures.cut_templates
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -m demo.fixtures.build_form_coords
```

각 원본 쪽은 A4 세로 페이지이며, 생성기는 서식 제목을 확인한 뒤 해당 쪽을 템플릿으로 만든다.

### 서식 글꼴

서식 위 입력 글자와 PDF 내보내기는 같은 Noto KR 글꼴을 사용한다. 입력 화면에는
WOFF2, PDF 합성에는 TTF 서브셋을 사용하며, 각 글꼴 폴더에 SIL OFL `OFL.txt`를
함께 둔다.

- 고딕: `frontend/src/assets/fonts/NotoSansKR/` — [Noto Sans KR 원본·라이선스](https://github.com/google/fonts/tree/main/ofl/notosanskr)
- 명조: `frontend/src/assets/fonts/NotoSerifKR/` — [Noto Serif KR 원본·라이선스](https://github.com/google/fonts/tree/main/ofl/notoserifkr)
- 서브셋: KS X 1001 한글 2,350자, ASCII 영문·숫자·문장부호, 서식 좌표의 라벨·보기와 가상 입력값에 쓰인 글자를 포함한다. 배경 PDF 문구는 원본 서식의 글꼴로 보존된다.
- 자동 글꼴 범위 검증: `run_p14_pdf_forms_scenarios`가 두 글꼴의 TTF/WOFF2/OFL 존재와 서식·가상 입력 글리프를 확인한다.

---

## 7. 알아 둘 것

- **판독(OCR)은 단계형 체인**이다. 생성 샘플의 고정 응답을 먼저 확인하고, 지원되는
  텍스트 레이어 없는 서류에는 전북AI OCR을 호출한다. 인증·통신·응답 오류 또는 서류별
  필수 항목·쪽 완전성 등 판독 검증 실패 시 로컬 OCR(Apple Vision 등)로 대체한다. 검증을
  통과한 결과는 환각 점수와 무관하게 사용하고, 잡음은 담당자 화면에 참고 표시한다.
  텍스트 PDF는 로컬 판독기와 PyMuPDF 텍스트 계층이 처리한다. 요청에는 temperature 0을
  사용하며 모델 특수 토큰은 제거한다. 전북AI는 좌표를 주지 않아 원본 위치 강조를 제공하지
  못한다. 실제 초본 시험은 전북AI 판독 검증을 통과하지 못해 현재 로컬 OCR로 대체되고
  있으며, 서류별 엔진을 실측 비교 중이다. 엔진·대체 사유·품질 메모는 담당자 화면에만
  표시한다 (`ocr/jbai.py`, `tests/run_p15_jbai_scenarios.py`).
- **점수는 신청자에게 절대 보이지 않는다**(공고문: "평가결과는 공개하지 않음").
  마이페이지 응답에 점수 관련 필드가 하나라도 섞이면 검증 스크립트가 잡는다.
- **미확정 가정값**에는 `(데모 추정치)` 라벨이 붙어 있다. 중위소득 100\~130% 환산
  기준선, 판독 신뢰도·화질 컷라인, 취업패키지 서식 구성, 선착순 기준 시각이
  여기 해당한다. 화면과 코드 양쪽에 같은 문구로 노출된다.
- **서식 좌표는 손으로 적지 않았다.** 원본 PDF의 표 선(`get_drawings`)과 글자
  원점(`get_text("rawdict")`)에서 뽑는다. `run_p7_scenarios`가 좌표를 다시 뽑아
  커밋된 JSON과 대조하므로, 좌표를 손으로 고치면 검증이 깨진다.
- 담당자는 신청자가 올린 원본 서류를 화면에서만 본다. 신청자는 본인이 작성한 서식만
  내려받을 수 있다. P4 시나리오는 담당자 화면·API와 원본 파일 경로를 검사하고, 신청자용
  서식 제공 파일만 명시적 허용 목록에 둔다.

## 8. 취업지원패키지 기준 확인 (2026 공고)

- [2026년 전북청년 취업지원패키지 모집 공고](https://youth.wanju.go.kr/board/view.wanju?boardId=BBS_0000001&dataSid=77474&menuCd=DOM_000000114001000000&paging=ok&startPage=1)는 면접비·정장비 각 5만원 최대 2회, 사진비 2만원 1회, 응시료 5만원 최대 2회와 항목별 추가 서류를 안내한다. 공고 페이지는 한도 횟수가 신청서·연간·생애 중 어디에 누적되는지 명시하지 않는다. 현재 데모는 기준의 `count_scope`를 설정할 수 있게 하고 기본값은 기존 동작인 신청서 단위다. 운영 전 담당 기관 확인이 필요하다.
- 공고는 면접비와 면접정장비 모두 면접확인서를 요구하지만, 정장 대여 회차를 특정 면접 회차와 연결하라고 정하지 않는다. 데모에서는 확인서 중복 업로드를 막도록 신청자가 연결 면접 회차를 고르게 하며, 이 연결 규칙은 접수서류 요구를 구현하기 위한 데모 가정이다.
- 면접비 대상 기업은 사업장 고용보험 가입자 5인 이상이며 결격 사유가 없어야 한다. 공개 공고에는 그 가입자 수를 어떤 서류나 조회 절차로 검증할지 적혀 있지 않아, 데모는 자동 판정을 하지 않는다.
- 공고 페이지는 인정 시험 목록을 별도 첨부 파일로 안내한다. 현재 공개 페이지 본문에는 목록이 없어 연도별 첨부 내용을 기준에 복사하지 않았다. 시험 목록 자동 판정은 담당 기관이 2026년 첨부 내용을 확정한 뒤 연결해야 한다.
