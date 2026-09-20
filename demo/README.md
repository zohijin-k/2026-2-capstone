# 데모 사이트 — 전북청년 두배적금 · 취업지원패키지 신청서류 자동 검토 시스템

신청자가 **종이·자필서명 없이** 신청을 끝내고, 담당자가 **파일을 한 번도 내려받지 않고**
심사를 끝내는 것을 보여주는 데모다. 사업 2종(두배적금 · 취업지원패키지)을 같은
파이프라인으로 처리한다.

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
│   ├── forms/          작성 서식 PDF 내보내기 (원본 위에 값 얹기)
│   └── tests/          P2~P7 게이트 검증 스크립트 (pytest 없이 실행)
├── frontend/           React + Vite (신청자 화면 · 담당자 화면)
├── fixtures/
│   ├── make_samples.py 시연용 더미 서류 생성기
│   ├── cut_templates.py     원본 시행지침 → 서식 템플릿 잘라내기 (2-up 주의)
│   ├── build_form_coords.py 템플릿 → 서식 좌표 맵 추출
│   ├── samples/        생성된 더미 PDF (gitignore)
│   ├── templates/      서식1·서식5 원본 쪽 (PDF 내보내기 템플릿, 커밋 대상)
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
# 터미널 1 — 백엔드 (저장소 루트에서)
uvicorn demo.backend.main:app --reload --port 8000
```

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

```bash
# 저장소 루트에서
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -m demo.backend.tests.run_p2_scenarios  # 업로드 즉시 판정
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -m demo.backend.tests.run_p3_scenarios  # 통합심사·채점
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -m demo.backend.tests.run_p4_scenarios  # 담당자 화면·다운로드 0회
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -m demo.backend.tests.run_p5_scenarios  # 취업지원패키지 분기
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -m demo.backend.tests.run_p6_scenarios  # 리셋 후 시연 10종 재현
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -m demo.backend.tests.run_p7_scenarios  # 작성 서식 PDF 내보내기
```

`run_p6_scenarios`는 **리셋 → S1~S10 연속 실행 → 기대값 대조**를 두 번 반복해,
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

## 6. 작성 서식 PDF 내보내기 (선택 기능)

작성된 서식을 **원본 서식과 같은 모양의 PDF**로 내보낸다. 원본 PDF를 템플릿으로
쓰고 그 위에 값·`✓`·전자서명을 얹는 방식이라, 결과물이 종이 서식과 구분되지 않는다.

```
GET /api/applications/{id}/forms           # 내보낼 수 있는 서식 목록
GET /api/applications/{id}/forms/서식1.pdf  # 인라인 (내려받지 않는다)
GET /api/applications/{id}/forms/서식5.pdf  # 서명란에 전자서명 합성
```

담당자 심사 화면의 서류 탭 오른쪽에 **"서식1 작성본 / 서식5 작성본"** 탭이 붙어,
업로드 서류와 나란히 브라우저 안에서 본다. 여기서도 내려받는 경로는 없다.

대상은 **두배적금 서식1·서식5 2종**이다. 취업지원패키지는 원본 서식이 사업계획서에
없어 내보낼 것이 없고, 서식2~4는 좌표 맵 구조만 비워 두었다.

템플릿과 좌표 맵은 **원본 시행지침 PDF에서 뽑아 만든 것**이다. 원본이 개정되면
아래 두 줄을 다시 돌린다 (저장소 루트에 시행지침 PDF가 있어야 한다).

```bash
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -m demo.fixtures.cut_templates
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -m demo.fixtures.build_form_coords
```

> ⚠️ 원본 PDF는 **2-up**이다. A4 가로 1장에 논리 2쪽이 들어 있어(물리 12쪽 = 논리
> 23·24쪽) 반드시 반쪽씩 잘라야 한다. `cut_templates.py`가 쪽번호로 검증한다.

---

## 7. 알아 둘 것

- **판독(OCR)은 3계층**이다. ① 파일명이 `fixtures/samples/`의 시연 파일과 같으면
  고정 결과(Tier1) ② 아니면 PDF 텍스트 레이어에서 실제로 읽는다(Tier2, PyMuPDF)
  ③ 스캔 이미지용 상용 API(Tier3)는 인터페이스만 있다. 시연 중 판독이 흔들려
  화면이 무너지는 일이 없도록 Tier1을 먼저 둔 것이고, 아무 PDF나 올려도 Tier2가
  받는다.
- **점수는 신청자에게 절대 보이지 않는다**(공고문: "평가결과는 공개하지 않음").
  마이페이지 응답에 점수 관련 필드가 하나라도 섞이면 검증 스크립트가 잡는다.
- **미확정 가정값**에는 `(데모 추정치)` 라벨이 붙어 있다. 중위소득 100~130% 환산
  기준선, 판독 신뢰도·화질 컷라인, 취업패키지 서식 구성, 선착순 기준 시각이
  여기 해당한다. 화면과 코드 양쪽에 같은 문구로 노출된다.
- **서식 좌표는 손으로 적지 않았다.** 원본 PDF의 표 선(`get_drawings`)과 글자
  원점(`get_text("rawdict")`)에서 뽑는다. `run_p7_scenarios`가 좌표를 다시 뽑아
  커밋된 JSON과 대조하므로, 좌표를 손으로 고치면 검증이 깨진다.
- 담당자 화면에는 **다운로드 버튼이 없다.** 백엔드에도 `attachment` 응답 경로가
  없고, 그 사실을 `run_p4_scenarios`가 정적 검사로 확인한다.
