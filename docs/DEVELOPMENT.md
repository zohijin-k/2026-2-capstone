# 개발 안내

OCR은 서류 사진이나 PDF에서 글자를 읽는 기술입니다.

## 목차

- [저장소와 브랜치](#저장소와-브랜치)
- [협업 규칙](#협업-규칙)
- [폴더 구조](#폴더-구조)
- [개발 환경과 실행](#개발-환경과-실행)
- [OCR 판독 설정](#ocr-판독-설정)
- [평가 도구](#평가-도구)
- [확인 및 테스트](#확인-및-테스트)
- [지켜야 할 원칙](#지켜야-할-원칙)
- [확인이 필요한 사항](#확인이-필요한-사항)
- [참고 자료](#참고-자료)

## 저장소와 브랜치

저장소는 GitHub의 `zohijin-k/2026-2-capstone`입니다. 최종 통합본은 `main`이며, 다른 브랜치를 내려받을 필요는 없습니다. 기존 clone은 `git checkout main && git pull`로 갱신합니다. git을 쓰지 않으면 저장소 첫 화면에서 브랜치가 `main`인지 확인하고 Code → Download ZIP으로 받습니다.

브랜치 안내 (2026-11-12 기준, 원격 브랜치 및 `origin/main` 병합 여부):

| 브랜치 | 상태 | 알려진 내용 |
|---|---|---|
| `main` | 기준 브랜치 | 원격 통합 브랜치 |
| `feat/applicant-check` | 병합됨 | 신청자 사전 검사 작업 |
| `feat/engine-v2` | 병합됨 | 엔진 v2 작업 |
| `feat/job-docs-align` | 미병합 | 취업 서류 판독기 수정. 병합 순서와 충돌 확인 필요 |
| `feat/job-docs-reader` | 미병합 | 내용 확인 중 |
| `feat/merge-demo-dashboard` | 미병합 | 브랜치 이름 기준 데모·대시보드 병합 작업 |
| `feat/own-default` | 병합됨 | own 기본 선택 작업 |
| `feat/own-fix` | 병합됨 | own 수정 작업 |
| `feat/own-ocr` | 병합됨 | 자체 OCR 작업 |

상태는 `git branch -r`과 `git branch -r --merged origin/main` 결과에 맞췄습니다. 원격에 없는 브랜치는 표에 넣지 않았습니다.
## 협업 규칙

1. 작업 전 `main`을 최신으로 받습니다: `git checkout main && git pull`.
2. 새 브랜치를 만듭니다: `git checkout -b feat/<작업-내용>`.
3. 커밋하고 push한 뒤 GitHub에서 `main`으로 PR(변경 내용을 검토받기 위한 병합 요청)을 만듭니다.
4. PR에 변경 내용을 적고 병합합니다. 병합한 브랜치는 삭제합니다.
5. `main`에 직접 push하지 않습니다.
6. 커밋 전 `git status`로 실제 서류, 환경 설정 파일, API 키가 섞이지 않았는지 확인합니다.

## 폴더 구조

| 경로 | 내용 |
|---|---|
| [`demo/`](../demo/README.md) | 신청자·담당자 데모, FastAPI(Python 웹 API 도구) 백엔드, React(화면 구성 라이브러리) 화면, 시나리오 확인 스크립트 |
| [`engine/`](../engine/README.md) | 기존 규칙 판정 엔진. 데모가 서류·자격 판정 파이프라인으로 사용합니다. |
| [`engine_v2/`](../engine_v2/README.md) | OCR 파이프라인·서류 추출기·분류기·평가 도구. `own` 모델 파일은 `models/`에 내려받으며 커밋하지 않습니다. |
| [`engine_v2/pipeline/ocr/`](../engine_v2/pipeline/ocr/) | OCR 공통 인터페이스와 엔진별 모듈 (`own.py` 포함) |
| [`engine_v2/classifier/`](../engine_v2/classifier/) · [`engine_v2/docs/`](../engine_v2/docs/) | 합성 서류 분류 실험 코드 · OCR/분류 설명 문서 |
| `engine_v2/models/` | 내려받은 OCR·분류 모델 파일 (gitignore, 커밋하지 않음) |
| [`dashboard/`](../dashboard/) | 현황 대시보드 코드 |
| [대시보드 옛 안내](archive/dashboard-README.md) | 현재 상태와 다를 수 있는 이전 문서 |
| [`docs/archive/`](archive/) | 옛 기록 보관 문서 |
| [`docs/`](./) | 기획·계획, 개발, 데모 환경 문서 |
| [`.trellis/`](../.trellis/workflow.md), [`.claude/`](../.claude/), [`AGENTS.md`](../AGENTS.md) | 작업 흐름, 에이전트 설정, 저장소 작업 지침 |
| `engine_v2/data/private/` | 실서류의 로컬 내부 평가용 보관 위치. 저장소에 커밋하지 않습니다. |

`demo_run.py`는 기존 `engine/` 단독 실행 예제입니다. 시스템 전체는 데모 백엔드와 프론트엔드를 실행합니다.

## 개발 환경과 실행

Python 3.12 이상, Node.js 20 이상이 필요합니다. macOS와 Linux에서 백엔드·프론트엔드를 실행할 수 있습니다. 데모 로컬 OCR은 macOS를 포함한 모든 환경에서 own이 기본이므로 macOS에서도 `python engine_v2/tools/fetch_own_models.py`로 모델을 설치해야 합니다.

저장소 루트에서 설치하고 시연 샘플을 생성합니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r demo/backend/requirements.txt
python -m pip install -r engine_v2/requirements.txt
python engine_v2/tools/fetch_own_models.py  # 모델은 저장소에 커밋하지 않음
cd demo/frontend
npm install
cd ../..
python -m demo.fixtures.make_samples
```

샘플은 가상 값으로 만든 PDF이며 `demo/fixtures/samples/`에 생성됩니다. 시나리오 확인 스크립트는 폴더가 없을 때 샘플을 자동 생성합니다.

백엔드와 프론트엔드를 별도 터미널에서 실행합니다.

```bash
# 터미널 1 — 저장소 루트
uvicorn demo.backend.main:app --reload --port 8000
```

```bash
# 터미널 2
cd demo/frontend
npm run dev
```

브라우저에서 <http://localhost:5173>을 엽니다. FastAPI 문서는 <http://localhost:8000/docs>입니다. 시연 전 데이터를 초기화할 때는 저장소 루트에서 `python -m demo.backend.reset`을 실행합니다.

## OCR 판독 설정

이번 제출에서는 전북AI를 사용하지 않습니다(연동 코드는 있으나 이번 제출에서는 사용하지 않음). JBAI_* 설정은 비워 둔 채 실행합니다. 판독 순서는 시연 고정 응답 → 로컬 OCR → PDF 텍스트입니다. 전북AI 연동 코드는 남아 있지만 이번 제출 판독 체인에서는 호출하지 않습니다.

데모 로컬 OCR은 macOS를 포함한 모든 환경에서 own이 기본입니다. 비어 있지 않은 `ENGINE_V2_OCR` 값이 있으면 이를 우선합니다. 기본 선택에서 own 모델 파일이 없을 때만 easyocr로 대체합니다. 명시적으로 own을 선택했는데 모델이 없거나 해시 확인·추론에 실패하면 다른 OCR 엔진으로 대체하지 않습니다. 모델 설치는 macOS에서도 필요합니다.

`engine_v2.engine.run`과 CLI(명령줄 도구)의 선택값은 `own`, `applevision`, `easyocr`, `paddle`입니다. `off`는 데모 전용 비활성화 값입니다. 공용 엔진 선택에 전북AI는 포함되지 않습니다.
## 평가 도구

`fetch_synth_fonts.py`는 합성 평가용 글꼴을 받고 `make_synth_eval.py`는 가상 문서 평가 세트를 만듭니다. `ocr_bench`로 own·Apple Vision 등 OCR 엔진을 비교할 수 있습니다. OCR은 서류 사진이나 PDF에서 글자를 읽는 기술입니다. 평가 정의와 한계, 실서류 평가의 개인정보 보호 방식은 [own OCR 설명](../engine_v2/docs/own-ocr.md)을 참고합니다. `extract_diag --safe-issue`는 값·인식 텍스트·파일명·좌표를 출력하지 않습니다.

```bash
python engine_v2/tools/fetch_synth_fonts.py
python engine_v2/tools/make_synth_eval.py
python -m engine_v2.tools.ocr_bench --synth engine_v2/data/synth_eval/manifest.json --engines own applevision
python -m engine_v2.tools.ocr_bench "<파일 경로>" --doc resident_abstract --engines own applevision
```

own의 현재 평가는 합성 서류 3종(주민등록초본·납부확인서·자격득실확인서 형태), 열화 조건과 ±2도 이내 회전을 포함합니다. 90도·180도 방향 보정은 없습니다. 기존 문서에서 보고한 실서류 관찰은 주민등록초본과 4대보험 가입내역에 한정되며 공개 안내에서는 식별정보와 수치 판독 결과를 공개하지 않습니다. 합성 자료 결과는 실제 서류 전반의 성능을 보장하지 않습니다.

자체 OCR 모델은 공개 사전학습 PP-OCRv5 mobile 검출·한국어 인식 모델의 ONNX 변환본이며, 모델을 직접 사전학습했다는 의미는 아닙니다. 데모 기본 연결과 2단계 학습은 진행 중입니다. 출처·라이선스, 모델 설치와 평가 방법은 [own OCR 설명](../engine_v2/docs/own-ocr.md)에 있습니다.

## 확인 및 테스트

테스트는 가상 데이터와 임시 저장소를 사용합니다. 시나리오 전체와 OCR 엔진 테스트는 저장소 루트에서 실행합니다.

```bash
for f in demo/backend/tests/run_p*_scenarios.py; do echo "== $f"; python -m demo.backend.tests.$(basename "$f" .py) || echo "FAILED $f"; done
python -m pytest engine_v2/tests -q
```

현재 실행 확인 결과 `engine_v2/tests`는 260개 통과, 3개 건너뜀입니다. 맥에는 합성 글꼴이 없어 일부 글꼴 의존 테스트가 건너뛰어질 수 있습니다. 시나리오 스크립트 18개를 실행해 1,776개 확인이 통과했습니다. 위 반복문은 한 시나리오가 실패해도 나머지를 계속 실행합니다. 파일 이름 순서상 P11\~P15가 P2\~P9보다 먼저 실행되므로, 앞에서 멈추면 뒤 시나리오 결과를 확인할 수 없습니다.

프론트엔드 타입 검사·린트·빌드는 다음과 같습니다.

```bash
cd demo/frontend
npx tsc -b && npx oxlint && npx vite build
```

하위 폴더별 기능과 추가 실행 방법은 [데모](../demo/README.md), [기존 엔진](../engine/README.md), [엔진 v2](../engine_v2/README.md), 대시보드 코드와 [대시보드 옛 안내](archive/dashboard-README.md)를 확인합니다.

자체 OCR의 제작 과정·평가·한계는 [제작 과정 기록](../engine_v2/docs/own-ocr-history.md)을 참고하세요.

## 지켜야 할 원칙

- 실제 서류는 로컬 내부 평가용 보관 위치에만 두고 저장소에 커밋하지 않습니다.
- 판정은 공고문에 근거한 규칙으로 합니다. OCR·모델은 문서를 읽는 데 씁니다.
- 신청자 화면에 배점·내부 판단 정보·서류 속 타인의 이름을 노출하지 않습니다.
- 파일 이름이 아니라 서류 내용으로 종류와 판정 근거를 판단합니다.
- 담당자는 신청자가 올린 원본 서류를 내려받지 않고 화면으로만 확인합니다. 신청자는 본인이 작성한 서식만 내려받을 수 있으며 P4 시나리오가 이 경계를 확인합니다.
- 값을 출력하는 점검 도구는 이름·주소·번호를 가립니다.
- OCR 모델·글꼴·패키지의 제3자 출처와 라이선스는 [제3자 고지](../THIRD_PARTY_NOTICES.md)와 [own OCR 설명](../engine_v2/docs/own-ocr.md)에서 확인합니다.
- API 키를 코드·로그·커밋에 넣지 않습니다.
- 모델 학습에는 개인정보가 없는 합성 데이터만 사용합니다. 실서류는 기관 내부 평가에만 사용하고 판독은 가능한 한 기관 내부 엔진으로 합니다. 외부 전송은 기관의 명시 확인 범위에서만 합니다. 주민등록번호 뒷자리는 응답 즉시 지우고 원문을 남기지 않습니다.

## 확인이 필요한 사항

- 혼합가입자가 제출할 서류와 건강보험료 합산 방식
- 공고문 표가 7인까지인 상태에서 8\~10인 상한표를 적용할 출처·기준
- 취업지원패키지 지원 횟수 누적 범위와 인정 시험 목록
- 담당자 심사 상태를 승인·보완요청·부적격·재검토 4종으로 전환할지

## 참고 자료

- `‘26년 전북청년 함께 두배적금 운영성과 및 ‘27년 운영계획.pdf` — 사업 개요, 2026년 운영 애로사항, 2027년 개선 방향
- `2026년 전북청년 함께 두배적금 상담(콜센터) 시스템 구축 및 운영 결과 보고서_주베스트인.pdf` — 콜센터 상담 데이터, 실무자 건의사항(통합 플랫폼, 자체 취소 기능, 온라인 서명 등)
