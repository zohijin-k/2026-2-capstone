제작 과정은 [own-ocr-history.md](own-ocr-history.md) 참고
# 자체 OCR 1단계

`own`은 공개 사전학습 PP-OCR 모델을 기관 내부 CPU에서 ONNX Runtime으로 추론하는 엔진이다. 직접 사전학습한 모델이라는 뜻은 아니다. 2단계에서 전북 서류 합성 데이터로 추가 학습한다. 미세조정과 판정·점수 규칙은 변경하지 않았다. demo 백엔드는 아래 기본 엔진 선택 규칙으로 연결한다.

## 기존 구조와 호환 계약

기존 `pipeline/ocr.py`를 `pipeline/ocr/__init__.py`로 이동했다. `engine_v2.pipeline.ocr` import와 `run_ocr(engine, png, size)` 인터페이스는 유지한다. Apple Vision은 정규화된 좌하단 좌표를 좌상단 픽셀로 변환하고, EasyOCR/Paddle은 다각형의 외접 사각형을 반환한다. `OcrWord(text, confidence, bbox_px)`의 confidence는 0~1, 좌표는 입력 이미지의 좌상단 원점 `(x0,y0,x1,y1)`이다. 텍스트 읽기 순서는 기존의 `(round(y0/15), x0)`를 따른다. 최초 OCR 도입에서는 기존 세 추출기를 수정하지 않았다. 아래 대시·발급일 수정에서는 형식 파서 입력만 정규화하며 판정·점수 규칙은 유지한다.

`own`은 DB 확률맵 → 윤곽선/영역 평균 점수 → polygon unclip → 원본 좌표 복원 → 원근 보정 crop → Korean CTC 순이다. 검출은 긴 변 최대 1600, 32배수 크기; 인식은 높이 48, 최소 폭 320이다. DB 임계값 0.3/box 점수 0.5/unclip 1.5를 고정했다. 세로 crop은 회전하지만 180도 방향 분류 모델은 포함하지 않는다. CPUExecutionProvider만 사용하며 스레드는 intra=2/inter=1이다. 네트워크 다운로드는 fetch 명령에서만 수행한다. 추론 시작 시 모든 파일 해시, 사전·출력 클래스 수, 모델 내장 문자 목록을 검증한다.

`engine_v2.engine.run`과 CLI는 `ENGINE_V2_OCR`를 우선하고, 없으면 macOS=`applevision`, 그 외=`own`이다. demo/backend 로컬 OCR 기본값은 macOS를 포함해 모든 기계에서 `own`이다. 비어 있지 않은 `ENGINE_V2_OCR` 명시 지정이 우선하며, 기본 선택에서 own 모델 파일이 없을 때에만 `easyocr`로 대체한다. 모델 감지는 실제 로더의 `own.MODEL_DIR`(기본 `engine_v2/models/own`)과 고정 자산 목록의 파일 존재 여부를 사용한다. 명시한 `own`의 모델 누락, 해시 검증 실패, 일반 추론 오류는 다른 OCR 엔진으로 대체하지 않는다. 대체 사유는 `demo.backend.ocr.localocr.engine_decision() -> tuple[str, str]`의 `(엔진, 사유)` 반환값과 대체 시 판독 호출당 한 줄의 경고 로그로만 확인한다. 대체가 없으면 사유는 빈 문자열이다. 결과의 `engine`에는 실제 사용한 엔진만 기록하며 `fallback_reason`·`quality_note`에 대체 사유를 쓰지 않는다. easyocr도 미설치이면 기존처럼 다음 계층으로 넘어간다. 모델 준비 경로·`fetch_own_models.py` 사용법과 engine_v2 CLI 기본값은 그대로다. 공용 로컬 엔진 선택지는 `own | applevision | easyocr | paddle`이며, `off`는 demo 어댑터의 비활성화 값이다. `jbai`는 별도 어댑터/벤치 경로이며 공용 `run_ocr` 선택지가 아니다. `extract_diag`는 `--engine own | applevision`을 명시적으로 지원한다.

취업지원 서류의 필수 항목 부재는 실제 페이지 출처로 구분한다. 모든 쪽을 글자층으로 읽었다면 부재를 확정하고 문서 신뢰도를 0.9로 유지한다. 응시일이 없으면 기존 `MISSING_REQUIRED_FIELD` 부적합만 반환한다. 한 쪽이라도 OCR을 거쳤다면 부재는 미판독일 수 있으므로 신뢰도 0.5와 실제 OCR 엔진을 기록하고, `LOW_OCR_CONFIDENCE`·`REQUIRED_FIELD_UNREADABLE`로 담당자 확인과 재촬영을 안내한다. 모든 쪽이 글자층일 때만 엔진을 `pdftext`로 표시한다. 필수 항목을 읽었을 때의 신뢰도 계산과 기존 판정 규칙은 유지하며, 엔진·대체 사유는 신청자 응답에 공개하지 않는다. 글자층 사용 기준은 engine_v2의 기존 `TEXT_LAYER_MIN_CHARS`를 따른다.

## 모델 선택과 라이선스

| 후보 | 검토 | 선택 |
|---|---|---|
| PaddleOCR 공식 원본/직접 ONNX 변환 | 가장 직접적인 출처지만 변환 도구체인과 별도 변환 검증 필요 | 미선택 |
| RapidAI RapidOCR PP-OCRv5 mobile ONNX | 관리되는 공개 변환 배포, 모델별 SHA256 공개, 작은 CPU 모델 | 선택 |
| monkt/paddleocr-onnx | Apache-2.0 표기와 Korean v5 제공, 검출은 큰 server 모델 | 미선택 |
| 이전 PP-OCRv3 Korean | 더 작은 구세대 후보; 이 작업에서 품질 비교는 미측정 | 미선택 |

선택 배포는 [RapidOCR 모델 목록](https://github.com/RapidAI/RapidOCR/blob/main/python/rapidocr/default_models.yaml)의 **v3.10.0** ModelScope 아티팩트다. 파일 URL은 fetch 스크립트에 고정하고 SHA256으로 태그 변경도 탐지한다. 원본 [PP-OCRv5 mobile det](https://huggingface.co/PaddlePaddle/PP-OCRv5_mobile_det) 및 [Korean mobile rec](https://huggingface.co/PaddlePaddle/korean_PP-OCRv5_mobile_rec)의 모델 카드는 Apache-2.0을 명시한다. [RapidOCR 코드](https://github.com/RapidAI/RapidOCR/blob/main/LICENSE)도 Apache-2.0이다. 사전은 [PaddleOCR v3.3.2](https://github.com/PaddlePaddle/PaddleOCR/tree/v3.3.2) `ppocr/utils/dict/ppocrv5_korean_dict.txt`, 동일 저장소 Apache-2.0이다. [다른 변환 후보](https://huggingface.co/monkt/paddleocr-onnx)의 라이선스도 Apache-2.0이다.

| 로컬 파일 | 버전/내용 | 바이트 | SHA256 |
|---|---|---:|---|
| det.onnx | RapidOCR v3.10.0 / ch_PP-OCRv5_det_mobile | 4,819,576 | `4d97c44a20d30a81aad087d6a396b08f786c4635742afc391f6621f5c6ae78ae` |
| rec.onnx | RapidOCR v3.10.0 / korean_PP-OCRv5_rec_mobile | 13,488,748 | `cd6e2ea50f6943ca7271eb8c56a877a5a90720b7047fe9c41a2e541a25773c9b` |
| korean_dict.txt | PaddleOCR v3.3.2 / 11,945 entries | 47,451 | `a88071c68c01707489baa79ebe0405b7beb5cca229f4fc94cc3ef992328802d7` |

DB/CTC 어댑터 코드는 이 저장소에서 구현했으며 upstream 소스를 복사하지 않았다. 저장소 자체 LICENSE는 현재 없으므로 새 코드의 별도 오픈소스 사용 허가는 프로젝트 소유자가 정해야 한다. 모델을 재배포할 때는 upstream Apache-2.0 라이선스·고지를 함께 보존해야 한다. 본 커밋에는 모델/사전 바이너리나 데이터 생성물을 넣지 않는다.

## 설치와 실행

```bash
.venv/bin/python -m pip install -r engine_v2/requirements.txt
.venv/bin/python engine_v2/tools/fetch_own_models.py
.venv/bin/python engine_v2/tools/make_synth_eval.py
.venv/bin/python -m engine_v2.tools.ocr_bench \
  --synth engine_v2/data/synth_eval/manifest.json \
  --engines own easyocr applevision jbai \
  --output engine_v2/data/synth_eval/bench.json
```

추가 의존성: `onnxruntime`(CPU 추론, MIT), `numpy`(텐서, BSD), `opencv-python-headless`(리사이즈/윤곽선/원근 crop, Apache-2.0), `pyclipper`(DB 다각형 확장, MIT). `python-dotenv`(BSD-3-Clause)는 선택적 `--env-file .env` 설정 로딩에 사용한다. 설정 값은 출력하지 않는다. PaddlePaddle·CUDA·GUI 라이브러리는 필요 없다. requirements는 macOS 전용 Vision 마커를 유지하며 추가 패키지는 macOS 지원 배포가 있다. 이번 설치 검증은 Linux Python 3.12에서만 수행했다.

모델이 없으면 fetch 명령을 포함한 오류를 반환한다. 손상된 기존 모델은 자동 덮어쓰지 않고 실패한다. 다운로드는 임시 파일에서 검증한 뒤 원자적으로 이동한다.

## 최초 평가 정의 (906ec68, 아래 재평가에서 읽기 순서 수정)

기본 seed와 가짜 값으로 초본·납부확인서·4대보험 형태 3종 × 7열화 21쪽을 만든다. 같은 문서의 clean/scan300/blur/noise/rotate(±2도 이내)/jpeg/phone(원근·조명)을 비교한다. `demo.fixtures.make_samples`의 문구 및 CJK TextWriter 렌더링 관례를 재사용한다. 기존 templates는 신청서/동의서이므로 이 세 증명서의 공식 양식으로 오용하지 않는다. 4대보험 형태는 기존 `nhis_acquisition_loss` 계약을 시험하기 위해 건강보험 자격득실 부제·표를 포함하는 **복합 합성 서식**이다. 공식 4대보험 서식 대응을 입증하지 않는다.

CER: NFC 정규화 후 모든 Unicode 공백을 제거, 대소문자·문장부호 유지. Levenshtein 편집거리 / max(정답 글자 수, 1); 삽입이 많으면 1을 넘을 수 있다. 줄 정답은 렌더링 문구에서 독립적으로 작성한다. 필드 정확도는 기존 추출기의 직렬화된 필드값과 정답의 완전 일치 비율이며 누락도 오답이다. 문서 종류는 manifest의 평가 라우팅에만 사용하며 이미지 파일명으로 인식/판정하지 않는다.

평균 신뢰도는 인식 영역 점수의 단순 평균이다. 신뢰도 구간 [0,.5), [.5,.8), [.8,.9), [.9,1]별로 전체 정답과 예측 문자열을 편집 정렬하고, 출력 문자마다 해당 영역 점수를 부여하여 정답률/평균 신뢰도/표본 수를 계산한다. 삭제 문자는 CER에 포함하되 출력 신뢰도가 없어 구간에서 제외한다. 이것은 모델 자체의 문자 확률 보정 평가와 다르다. 점수는 판정 확률이 아니다.

시간은 첫 모델 로드가 포함된 한 번의 실행 wall time이며 별도 warm-up/반복 측정은 하지 않았다. 엔진 미설치/플랫폼 불일치/키 미설정은 skip으로 기록한다. 합성 출력도 기본적으로 기존 공용 `mask_text`를 사용한다. `--unmasked-synthetic`만 합성 결과의 텍스트 가림을 해제한다. 실서류 가림 함수 자체는 변경하지 않았다.

## 한계와 2단계

합성 3개 문서/한 폰트는 실제 서류 일반화 성능을 보장하지 않는다. 주민번호는 생년월일·성별 뒤 별표만 사용한다. 표의 작은 숫자, 회전/원근의 읽기 순서, 장문 crop, 180도 뒤집힌 입력, 직인/손글씨, 실제 복잡한 레이아웃은 추가 평가가 필요하다. `OcrWord`는 문자 하나가 아닌 검출 텍스트 영역이어서 셀 병합이 필드 추출 정확도에 영향을 준다.

2단계는 전북 서류의 다양한 합성 폰트·표·날짜·금액·주소를 늘리고, 템플릿/값/폰트 단위로 학습·검증·시험을 분리한다. Korean 인식 모델을 우선 미세조정하고 검출 모델은 누락 분석 후 별도 판단한다. 학습 환경의 Paddle 프레임워크는 추론 requirements와 분리한다. ONNX 재변환 후 고정 시험 세트의 CER/필드 정확도/지연/보정을 기존 모델과 비교하여 회귀가 없을 때만 교체한다. 실서류 평가는 별도의 승인된 내부 환경에서 수행한다.

## 최초 합성 벤치 결과 (906ec68, 수정 전 CER)

| 엔진 | 서류 | 열화 | CER | 필드 일치 | 초/쪽 | 평균 신뢰도 |
|---|---|---|---:|---:|---:|---:|
| own | resident_abstract | clean | 0.0116 | 4/4 | 1.672 | 0.995 |
| own | resident_abstract | scan300 | 0.0116 | 4/4 | 1.360 | 0.993 |
| own | resident_abstract | blur | 0.1628 | 4/4 | 1.112 | 0.989 |
| own | resident_abstract | noise | 0.0116 | 4/4 | 1.245 | 0.986 |
| own | resident_abstract | rotate | 0.0000 | 4/4 | 1.119 | 0.988 |
| own | resident_abstract | jpeg | 0.0000 | 4/4 | 1.100 | 0.987 |
| own | resident_abstract | phone | 0.0000 | 2/4 | 1.189 | 0.974 |
| own | nhis_payment | clean | 0.0000 | 6/6 | 1.206 | 0.999 |
| own | nhis_payment | scan300 | 0.0000 | 6/6 | 1.235 | 0.999 |
| own | nhis_payment | blur | 0.0000 | 6/6 | 1.131 | 0.997 |
| own | nhis_payment | noise | 0.0633 | 6/6 | 1.310 | 0.998 |
| own | nhis_payment | rotate | 0.0000 | 6/6 | 1.133 | 0.995 |
| own | nhis_payment | jpeg | 0.0000 | 6/6 | 1.145 | 0.991 |
| own | nhis_payment | phone | 0.0000 | 5/6 | 1.173 | 0.993 |
| own | nhis_acquisition_loss | clean | 0.0244 | 6/6 | 1.207 | 0.999 |
| own | nhis_acquisition_loss | scan300 | 0.0000 | 6/6 | 1.276 | 0.998 |
| own | nhis_acquisition_loss | blur | 0.0244 | 6/6 | 1.336 | 0.997 |
| own | nhis_acquisition_loss | noise | 0.0000 | 6/6 | 1.278 | 0.996 |
| own | nhis_acquisition_loss | rotate | 0.0000 | 6/6 | 1.185 | 0.998 |
| own | nhis_acquisition_loss | jpeg | 0.0854 | 6/6 | 1.238 | 0.991 |
| own | nhis_acquisition_loss | phone | 0.0000 | 4/6 | 1.199 | 0.997 |
| easyocr | 전체 | SKIP: easyocr 미설치 | — | — | — | — |
| applevision | 전체 | SKIP: macOS 전용 | — | — | — | — |
| jbai | 전체 | SKIP: JBAI_API_KEY 미설정 | — | — | — | — |

EasyOCR 미설치로 실제 own 대 EasyOCR 우열은 아직 판단할 수 없다. 휴대폰 원근 열화에서는 CER가 0이어도 추출 필드가 실패한다. 글자 인식 성능과 필드 추출 성능을 별도로 평가해야 한다.

보정: [0.9,1.0] 구간 3,457문자, 실제 정답률 98.901%, 평균 점수 98.933%. [0.5,0.8) 구간은 1문자뿐으로 해석할 수 없고 다른 구간은 표본이 없다.

## 최초 회귀 검증 (906ec68)

기준 커밋 0dced76, feat/own-ocr. 기존 테스트 파일과 demo/backend 변경 없음.

| 검증 | 통과 | 실패 |
|---|---:|---:|
| fetch 모델·사전 SHA256 | 3 | 0 |
| pytest (기존 70 + 새 단위 13 + 통합 2) | 85 | 0 |
| run_p11_criteria_scenarios.py | 38 | 0 |
| run_p12_subsidy_criteria_scenarios.py | 29 | 0 |
| run_p13_household_scenarios.py | 26 | 0 |
| run_p14_pdf_forms_scenarios.py | 8 서식 검증 | 0 |
| run_p15_jbai_scenarios.py | 129 | 0 |
| run_p2_scenarios.py | 53 | 0 |
| run_p3_scenarios.py | 150 | 0 |
| run_p4_scenarios.py | 182 | 0 |
| run_p5_scenarios.py | 152 | 0 |
| run_p6_scenarios.py | 249 | 0 |
| run_p7_scenarios.py | 238 | 0 |
| run_p8_localocr_scenarios.py | 89 | 0 |
| run_p9_identity_scenarios.py | 85 | 0 |
| tsc -b / oxlint / vite build | 모두 성공 | 0 |

시나리오는 지정된 중단하지 않는 반복문 그대로 실행했다. 샌드박스에서는 TestClient 시작이 정지하여 샌드박스 밖에서 재실행했고, 로그 확인까지 완료했다. 프론트에는 기존 StatusBadge.tsx Fast Refresh 경고 1건과 Vite 큰 청크 안내가 있다. 생성물과 벤치 JSON은 gitignore 대상이다.

## 평가 신뢰성 재점검 (2026-11-11, 기준 906ec68)

기존 21쪽/seed를 그대로 재실행해 이전 CER을 모두 재현했다. 정답 문구와 OCR 영역을 비교한 결과 **정답 오류 0건, 정규화 오류 0건, 실제 글자 인식 오류 0건**이었다. 8개 비영 CER 행은 모두 읽기 순서 문제다. 이 결론은 이 21쪽에만 적용하며 새 시험 세트나 실서류 성능을 뜻하지 않는다.

원인은 `OcrResult.text`의 `(round(y0/15), x0)` 정렬이다. 초본 clean의 행 번호 `1`은 y0=1194.2(버킷 80), 같은 행의 `본인`은 1178.8(79)이어서 숫자가 행 뒤로 이동했다. 납부 noise는 `2025.10` y0=1328.1(89), `100,000` y0=1327.0(88)로 **1.1px 차이**가 열 순서를 바꿨다. 가입 JPEG의 `자격취득일` 1148.6(77), `자격상실일` 1145.5(76)도 같은 원인이다. 흐림/잡음으로 검출 bbox가 조금 바뀌면 CER이 불연속적으로 튀었다. 엔진의 기본 텍스트 순서와 추출기는 그대로 두고 평가 문자열 구성만 고쳤다.

다음은 기존 전역 편집 정렬의 상위 글자 쌍이다. `∅`는 삽입/삭제이며 각 쌍 뒤 숫자는 횟수다. 순서 오류에서는 치환처럼 보이는 쌍도 발생하므로 실제 오인식 혼동표로 해석하면 안 된다. 원본 OCR 영역을 기하학적으로 다시 정렬하면 모든 쌍이 사라진다.

| 서류 | 열화 | 이전 CER | 분류 / 조치 | 상위 정답→인식 쌍 | 수정 CER |
|---|---|---:|---|---|---:|
| 초본 | clean | 0.0116 | 줄·열 순서 / 높이 기준 행 묶기 | ∅→1 ×1, 1→∅ ×1 | 0.0000 |
| 초본 | scan300 | 0.0116 | 줄·열 순서 / 높이 기준 행 묶기 | ∅→1 ×1, 1→∅ ×1 | 0.0000 |
| 초본 | blur | 0.1628 | 줄·열 순서 / 높이 기준 행 묶기 | 인→∅ ×1, 본→∅ ×1, ∅→인 ×1, ∅→본 ×1, ∅→호 ×1, ∅→번 ×1 | 0.0000 |
| 초본 | noise | 0.0116 | 줄·열 순서 / 높이 기준 행 묶기 | ∅→1 ×1, 1→∅ ×1 | 0.0000 |
| 초본 | rotate | 0.0000 | 이상 없음 / 유지 | 없음 | 0.0000 |
| 초본 | jpeg | 0.0000 | 이상 없음 / 유지 | 없음 | 0.0000 |
| 초본 | phone | 0.0000 | 이상 없음 / 유지 | 없음 | 0.0000 |
| 납부 | clean | 0.0000 | 이상 없음 / 유지 | 없음 | 0.0000 |
| 납부 | scan300 | 0.0000 | 이상 없음 / 유지 | 없음 | 0.0000 |
| 납부 | blur | 0.0000 | 이상 없음 / 유지 | 없음 | 0.0000 |
| 납부 | noise | 0.0633 | 줄·열 순서 / 높이 기준 행 묶기 | 0→1 ×1, 0→. ×1, ,→5 ×1, 0→2 ×1, 1→2 ×1, 1→0 ×1 | 0.0000 |
| 납부 | rotate | 0.0000 | 이상 없음 / 유지 | 없음 | 0.0000 |
| 납부 | jpeg | 0.0000 | 이상 없음 / 유지 | 없음 | 0.0000 |
| 납부 | phone | 0.0000 | 이상 없음 / 유지 | 없음 | 0.0000 |
| 가입 | clean | 0.0244 | 줄·열 순서 / 높이 기준 행 묶기 | 입→∅ ×1, 가→∅ ×1, ∅→입 ×1, ∅→가 ×1 | 0.0000 |
| 가입 | scan300 | 0.0000 | 이상 없음 / 유지 | 없음 | 0.0000 |
| 가입 | blur | 0.0244 | 줄·열 순서 / 높이 기준 행 묶기 | 입→∅ ×1, 가→∅ ×1, ∅→입 ×1, ∅→가 ×1 | 0.0000 |
| 가입 | noise | 0.0000 | 이상 없음 / 유지 | 없음 | 0.0000 |
| 가입 | rotate | 0.0000 | 이상 없음 / 유지 | 없음 | 0.0000 |
| 가입 | jpeg | 0.0854 | 줄·열 순서 / 높이 기준 행 묶기 | 입→∅ ×1, 가→∅ ×1, ∅→입 ×1, ∅→가 ×1, ∅→일 ×1, ∅→득 ×1 | 0.0000 |
| 가입 | phone | 0.0000 | 이상 없음 / 유지 | 없음 | 0.0000 |

초본 blur는 이름·주민번호 라벨 및 `본인`의 순서만 바뀌어 CER .1628이었고, 추출기는 별도의 높이 기준 행 묶기를 사용하여 4/4를 유지했다. 기존 phone은 OCR 문자열은 정확하지만 초본 이름이 `한자`로 추출되고 이력 행이 누락되어 2/4, 납부는 보험료 필드 누락으로 5/6, 가입은 가입구분·취득일 누락으로 4/6이었다. 필드 정확도는 수정하지 않았다.

기존 phone은 A4 2480×3509 수준 해상도를 유지하고, 모서리 1–6% 이동과 매끄러운 곱셈 조명만 적용했다. 국소 그림자·초점 흐림·센서 잡음·해상도 손실은 없었다. 따라서 글자 인식 관점에서는 쉬웠지만 표 구조 추출에는 이미 영향을 주었다. CER 0만으로 휴대폰 촬영을 대표한다고 볼 수 없다.

### 현재 CER 계산 계약

- NFC 조합 후 모든 Unicode 공백을 제거한다. 대소문자, 문장부호, 숫자, 마스킹 별표를 유지하며 유사 글자 치환 규칙은 추가하지 않는다.
- 합성 평가에서만 알려진 `page_transform`의 역행렬로 OCR bbox를 원래 캔버스 좌표에 옮긴다. 보정 실험은 검출 보정행렬과 합성 행렬을 합성한다. 이는 **평가 순서의 기준 좌표만** 바꾸며 OCR 이미지, 인식 글자, 추출기 입력을 고치지 않는다. 실제 촬영에서는 이 정답 기하를 알 수 없으므로 배포 OCR 읽기 순서 성능과 다르다.
- 새 manifest는 렌더링 행 baseline 위치를 제공한다. 역변환 bbox 중심을 가장 가까운 baseline에 배정하되, 해당 baseline의 인접 행 간격 최솟값 × 0.45 이내일 때만 같은 행으로 묶는다. 먼 배경 검출은 지우지 않고 원래 중심 위치의 별도 행으로 남긴다. 행 안은 왼쪽→오른쪽이다. 행 위치 없는 기존 manifest는 중심 차이 ≤ 해당 글자 높이 × 0.6의 행 묶기를 사용한다. 줄 정답과 텍스트 유사도로 짝짓거나 최적 순열을 찾지 않는다. 전체 문자열을 한 번만 Levenshtein 정렬하며 행 경계 공백은 제외된다.
- 삽입·삭제·치환 비용은 각각 1. CER = 편집 수 / max(정답 NFC 비공백 문자 수, 1). 1 초과도 허용한다. 동률은 대각선(동일/치환), 삭제, 삽입 순으로 결정한다.
- 기존 엔진 문자열의 `raw_stream_cer`도 JSON에 남겨 순서 영향이 숨지 않게 한다. 신뢰도 보정은 새 평가 순서와 동일하게 정렬한다. 문자별 점수는 영역 점수를 상속하며 삭제는 CER에만 포함한다.
- 필드 O/X는 기존 추출기의 직렬화된 값과 GT 완전 일치이고 누락은 X다. 판정·점수·추출 로직은 바꾸지 않았다.

단어 경계에 분리된 한글 자모도 전체 NFC에서 조합한다. 이때 신뢰도 관측 수가 문자 수와 어긋나던 잠재 오류를 추가로 수정했다(기존 21쪽 이상치 원인은 아님). 여러 문자/영역이 한 글자로 조합되면 기여 점수의 최솟값을 사용한다. 역변환한 외접 bbox는 원래 회전 다각형의 근사치다. 새 세트 첫 점검에서 강한 명조 초본의 긴 bbox 높이가 300–500px로 부풀어 다른 행을 합치면서 CER .2035를 만들었다. 이를 실제 인식 오류로 보고하지 않도록 새 manifest에서는 위의 알려진 행 위치에 기반한 기하 매칭을 사용한다. 합성 정답 기하를 활용한 인식 CER이며 배포 읽기 순서 성능을 주장하지 않는다.

### 글꼴·학습/시험 분리·휴대폰 생성

고정 Google Fonts commit `1c96438dec81b2b5078557d91315e31fb29b9462`를 사용한다. 세 글꼴 모두 SIL Open Font License 1.1이며 OFL 고지도 받아 SHA256을 확인한다. 글꼴·고지 파일은 기존 `engine_v2/data/` gitignore 안에만 받는다.

| 글꼴 / 분할 | 고정 파일 URL | 라이선스 | SHA256 |
|---|---|---|---|
| NanumGothic-Regular.ttf / test | [고정 원본](https://raw.githubusercontent.com/google/fonts/1c96438dec81b2b5078557d91315e31fb29b9462/ofl/nanumgothic/NanumGothic-Regular.ttf) | [OFL 1.1](https://raw.githubusercontent.com/google/fonts/1c96438dec81b2b5078557d91315e31fb29b9462/ofl/nanumgothic/OFL.txt) | `76f45ef4a6bcff344c837c95a7dcc26e017e38b5846d5ae0cdcb5b86be2e2d31` |
| NanumMyeongjo-Regular.ttf / test | [고정 원본](https://raw.githubusercontent.com/google/fonts/1c96438dec81b2b5078557d91315e31fb29b9462/ofl/nanummyeongjo/NanumMyeongjo-Regular.ttf) | [OFL 1.1](https://raw.githubusercontent.com/google/fonts/1c96438dec81b2b5078557d91315e31fb29b9462/ofl/nanummyeongjo/OFL.txt) | `7ed9e8653a8ed04285d51dc343ffea6eb3d9c73afc27383ea8929ee4ffd03205` |
| NanumGothicCoding-Regular.ttf / train | [고정 원본](https://raw.githubusercontent.com/google/fonts/1c96438dec81b2b5078557d91315e31fb29b9462/ofl/nanumgothiccoding/NanumGothicCoding-Regular.ttf) | [OFL 1.1](https://raw.githubusercontent.com/google/fonts/1c96438dec81b2b5078557d91315e31fb29b9462/ofl/nanumgothiccoding/OFL.txt) | `787effd7efed2abca88ade231faa8191f4e9fcf85b1805a13ee1dc3724b72089` |

시험은 Nanum Gothic/Myeongjo × inline_header_v1, 학습은 Nanum Gothic Coding × stacked_header_v1을 사용한다. 학습 서식은 라벨 아래에 값을 놓고 헤더 열과 본문 위치를 바꾼 별도 배치다. 서류 종류는 공유하되 서식 가족·글꼴은 겹치지 않는다. `--fonts`는 해당 split에 배정된 글꼴만 허용하며 열화/seed로 나누지 않는다. 이번에는 시험 48쪽만 생성·평가했다. 값 자체는 공유하므로 값 분포까지 분리한 학습 성능 검증은 향후 별도로 필요하다.

| 휴대폰 조건 | 각 모서리 x/y 이동 | 배경 여백 | x/y 조명 기울기 | 그림자 불투명도 | 흐림 σ(px) |
|---|---|---|---|---|---|
| 약 | 독립 ±3–5% | 7% | 13% / 8% | 20% | .65 |
| 강 | 독립 ±6–8% | 10% | 24% / 16% | 38% | 1.15 |

모서리별 부호를 교차 배정하여 단순 축소가 아닌 사다리꼴·기울기를 만들고 전체 방향 부호는 seed로 정한다. 밝기 변화와 비스듬한 국소 그림자, 나무색 배경 노출을 포함한다. 고정 seed로 재현 가능하며 실제 카메라 분포에 보정된 모델은 아니다. 원근 보정 함수는 Canny/밝기 임계값 윤곽에서 가장 큰 볼록 사각형을 찾고, 화면 테두리/작은 영역을 제외한 뒤 변 길이 기준으로 펼친다. 정답 모서리를 사용하지 않는다. 검출 실패 시 원본과 applied=False를 반환한다. 엔진 기본 동작은 꺼진 상태 그대로다.

```bash
.venv/bin/python -m engine_v2.tools.fetch_synth_fonts
.venv/bin/python -m engine_v2.tools.make_synth_eval --split test
.venv/bin/python -m engine_v2.tools.ocr_bench \
  --synth engine_v2/data/synth_eval/revised/manifest.json \
  --engines own --rectify-phone --unmasked-synthetic \
  --output engine_v2/data/synth_eval/revised/bench.json
# 후속 학습용 생성 예: 이번 작업에서는 실행/평가하지 않음
.venv/bin/python -m engine_v2.tools.make_synth_eval --split train \
  --output engine_v2/data/synth_eval/train
```

### 맥의 실서류 벤치: 값 미출력

아래 private 경로는 실행 예시일 뿐이며 이 작업에서는 해당 디렉터리를 만들거나 읽지 않았다.

```bash
.venv/bin/python -m engine_v2.tools.ocr_bench \
  engine_v2/data/private/초본.pdf \
  --gt engine_v2/data/private/초본.gt.json \
  --doc resident_abstract --engines own applevision jbai
# 명시할 때만 숫자/OX JSON 저장
.venv/bin/python -m engine_v2.tools.ocr_bench \
  engine_v2/data/private/초본.pdf \
  --gt engine_v2/data/private/초본.gt.json \
  --engines own applevision jbai --env-file .env --out metrics.json
# 4대보험 가입내역: make_gt --doc insurance_4로 만든 정답 형식 그대로 사용
.venv/bin/python -m engine_v2.tools.ocr_bench \
  <4대보험 PDF 경로> \
  --gt engine_v2/data/private/insurance_4.gt.json \
  --doc insurance_4 --engines own applevision jbai --env-file .env
```

JBAI는 기존 `JBAI_API_KEY`와 `JBAI_ALLOW_REAL_DOCS=true` 설정이 모두 필요하며 설정값은 출력하지 않는다. 미설정/비맥 Apple Vision/미설치 모델은 건너뛰고 계속한다. 이유 코드는 1=플랫폼, 2=설치/모델, 3=키 미설정, 4=실서류 전송 동의 미설정, 5=엔진/추출 예외다. `skipped/failed/fallback`은 O/X이며 다른 엔진으로 대체하지 않는다. 원격 신뢰도는 제공되지 않아 `-1`, `confidence_available=X`로 표시한다.

입력·OCR·추출·저장 단계에서 Python stdout/stderr와 native fd 1/2 출력을 폐기한다. 예외 본문, 파일명, 정답 값, OCR 문자열, 사용자 정의 필드 키를 출력하지 않는다. 출력 키는 코드의 허용 목록으로 고정한다. 이 출력 억제는 프로세스 전체에 적용되므로 단일 CLI 용도다. `--out` 생략 시 결과 파일/디렉터리는 만들지 않으며 지정해도 상위 폴더를 자동 생성하지 않는다. PDF 텍스트 레이어도 300dpi로 렌더링하여 모든 엔진에 OCR을 실행한다.

단일 필드 CER는 위 NFC/공백 정책을 공유한다. 월별은 월→금액 순서, 이력은 category/acquired/lost 값 순서, 조회기간은 시작/끝 순서의 값 전용 문자열을 내부 비교하고 JSON 스키마 키/구두점은 분모에 넣지 않는다. 빈 구조 셀은 `␀`, 필드 전체 누락은 빈 문자열이다. `address_contains`는 부분 정답이므로 각 지정 부분의 최소 연속 부분문자열 편집거리 합/지정 글자 수, `move_in_dates`는 날짜별 최근접 날짜 CER 평균이다. 이 두 항목은 전체 주소/전체 이력 CER가 아니며 미지정 항목의 추가는 벌점이 없다. O/X는 make_gt 계약의 완전 일치/포함 여부이고 임의 유사도 허용은 없다.

`insurance_4` 출력 필드 키는 `name/birth_date/issue_date/document_number/rows`로 고정한다. `rows`는 make_gt 입력 순서(국민연금→건강보험→산재보험→고용보험), 추출은 문서 행 순서를 그대로 유지하고 재정렬하거나 최적 대응시키지 않는다. 각 행은 `insurance/name/subscriber_category/management_number/workplace_name/acquired/received/status` 순서의 값 전용 문자열로 CER를 비교한다. bbox·신뢰도·JSON 키/구두점은 제외한다. D의 정답 비교와 같이 생략한 셀은 빈 문자열, acquired의 null은 빈 문자열, received의 null/하이픈 표기는 빈 문자열로 정규화한다. CER 스트림에서는 빈 셀을 `␀`로 표시하고 전체 필드 누락은 빈 문자열로 둔다. 미가입 행도 비교하며, 행 순서나 개수가 다르면 O/X는 X다.

JBAI의 4대보험 지원은 벤치 전용 변환 계층이다. 인식한 머리말과 6열 표의 순서를 임시 격자에 배치해 D의 `insurance_4.extract`를 재사용한다. 실제 bbox로 해석하지 않으며 반환 bbox는 비운다. 표가 없거나 지원하지 않는 구조는 값을 추측해 채우지 않는다. 가린 주민번호는 앞자리·성별 자리로 생년월일만 얻고 뒷자리를 복원하지 않는다. 기본 엔진의 판정·점수·추출기는 바꾸지 않는다. macOS Vision과 실제 JBAI 응답은 이 WSL 기계에서 검증하지 않았으며 합성 응답 재생으로 변환 경로를 검증한다.

D의 가상 좌표 샘플을 이미지로 렌더링한 own CPU 실서류 CLI 실행 결과(실서류가 아님):

```json
{
  "engine": "own",
  "skipped": "X",
  "failed": "X",
  "fallback": "X",
  "reason_code": 0,
  "pages": 1,
  "seconds_per_page": 2.564465,
  "mean_confidence": 0.9786820496831622,
  "confidence_available": "O",
  "fields": {
    "name": {
      "match": "O",
      "cer": 0.0
    },
    "birth_date": {
      "match": "O",
      "cer": 0.0
    },
    "issue_date": {
      "match": "X",
      "cer": 1.0
    },
    "document_number": {
      "match": "O",
      "cer": 0.0
    },
    "rows": {
      "match": "O",
      "cer": 0.0
    }
  }
}
```

같은 실행에서 Apple Vision은 플랫폼 사유 코드 1, JBAI는 키 미설정 코드 3으로 건너뛰었다. 가짜 정답·인식 문자열·파일명은 출력 전체에서 검출되지 않았다. 이 합성 이미지에서는 발급일이 X/CER 1.0이며 추출기 보정은 하지 않았다. 이 한 번의 실행은 실서류 정확도나 세 엔진 성능 비교 결과가 아니다.

실서류 모드 시간은 초기화+OCR+필드 추출 wall time/쪽 수이며 입력 래스터화는 제외한다. 합성 벤치 시간은 OCR wall time+보정 함수 시간이며 이미지 파일 IO/PNG 인코딩/필드 추출은 제외한다. 서로 다른 시간 정의를 직접 같은 지표로 비교하지 않는다.

가짜 GT를 넣은 실제 own 합성 실행의 값 없는 출력 발췌(의도적으로 name GT를 다르게 입력):

```json
{
  "engine": "own", "skipped": "X", "failed": "X", "fallback": "X",
  "pages": 1, "seconds_per_page": 1.571746, "mean_confidence": 0.995086,
  "fields": {
    "name": {"match": "X", "cer": 0.5},
    "birth_date": {"match": "O", "cer": 0.0},
    "issue_date": {"match": "O", "cer": 0.0}
  }
}
```

새 테스트는 성공·오류·미설정·잘못된 인자, Python/native 출력, 실제 own 합성 실행의 stdout+stderr+`--out` 전체에서 가짜 GT와 인식 문자열이 하나도 남지 않음을 확인한다. macOS Apple Vision 및 실제 JBAI 호출은 이 기계에서 실행하지 않았다.

### 새 시험 벤치 (WSL Ubuntu 24.04, own CPU, seed 20261111)

48개 시험 입력 + 휴대폰 12개 보정 실험 = 60회, 엔진 실패 0. 단일 실행이며 첫 행은 모델 초기화 시간을 포함한다. 인식 CER는 위 합성 기하를 이용한 순서로 계산한다. 점수 반올림 1.000은 100% 정답 보장을 뜻하지 않는다. 시간은 반복 분산을 측정하지 않은 참고치다.

| 서류 | 열화 | 글꼴 | CER | 필드 | 초/쪽 | 신뢰도 |
|---|---|---|---:|---:|---:|---:|
| 초본 | clean | 고딕 | 0.0000 | 4/4 | 1.621 | 0.993 |
| 초본 | scan300 | 고딕 | 0.0000 | 4/4 | 1.330 | 0.994 |
| 초본 | blur | 고딕 | 0.0000 | 4/4 | 1.129 | 0.994 |
| 초본 | noise | 고딕 | 0.0000 | 4/4 | 1.214 | 0.986 |
| 초본 | rotate | 고딕 | 0.0000 | 4/4 | 1.132 | 0.994 |
| 초본 | jpeg | 고딕 | 0.0000 | 4/4 | 1.061 | 0.986 |
| 초본 | phone_weak | 고딕 | 0.0058 | 1/4 | 1.142 | 0.970 |
| 초본 | phone_weak+rectified | 고딕 | 0.0000 | 4/4 | 1.430 | 0.994 |
| 초본 | phone_strong | 고딕 | 0.0116 | 0/4 | 1.124 | 0.922 |
| 초본 | phone_strong+rectified | 고딕 | 0.0116 | 0/4 | 1.440 | 0.922 |
| 납부 | clean | 고딕 | 0.0000 | 6/6 | 1.267 | 0.999 |
| 납부 | scan300 | 고딕 | 0.0000 | 6/6 | 1.247 | 1.000 |
| 납부 | blur | 고딕 | 0.0000 | 6/6 | 1.104 | 0.989 |
| 납부 | noise | 고딕 | 0.0000 | 6/6 | 1.252 | 0.998 |
| 납부 | rotate | 고딕 | 0.0000 | 6/6 | 1.172 | 0.999 |
| 납부 | jpeg | 고딕 | 0.0000 | 6/6 | 1.128 | 0.993 |
| 납부 | phone_weak | 고딕 | 0.0063 | 2/6 | 1.220 | 0.965 |
| 납부 | phone_weak+rectified | 고딕 | 0.0000 | 6/6 | 1.508 | 0.995 |
| 납부 | phone_strong | 고딕 | 0.0127 | 2/6 | 1.334 | 0.941 |
| 납부 | phone_strong+rectified | 고딕 | 0.0127 | 2/6 | 1.454 | 0.941 |
| 가입 | clean | 고딕 | 0.0000 | 6/6 | 1.120 | 0.998 |
| 가입 | scan300 | 고딕 | 0.0000 | 6/6 | 1.266 | 0.997 |
| 가입 | blur | 고딕 | 0.0000 | 6/6 | 1.148 | 0.998 |
| 가입 | noise | 고딕 | 0.0000 | 6/6 | 1.230 | 0.997 |
| 가입 | rotate | 고딕 | 0.0000 | 6/6 | 1.167 | 0.999 |
| 가입 | jpeg | 고딕 | 0.0000 | 6/6 | 1.222 | 0.992 |
| 가입 | phone_weak | 고딕 | 0.0061 | 1/6 | 1.274 | 0.970 |
| 가입 | phone_weak+rectified | 고딕 | 0.0000 | 6/6 | 1.522 | 0.999 |
| 가입 | phone_strong | 고딕 | 0.0122 | 0/6 | 1.387 | 0.937 |
| 가입 | phone_strong+rectified | 고딕 | 0.0122 | 0/6 | 1.529 | 0.937 |
| 초본 | clean | 명조 | 0.0058 | 2/4 | 1.201 | 0.988 |
| 초본 | scan300 | 명조 | 0.0058 | 2/4 | 1.346 | 0.991 |
| 초본 | blur | 명조 | 0.0233 | 3/4 | 1.191 | 0.971 |
| 초본 | noise | 명조 | 0.0000 | 4/4 | 1.333 | 0.980 |
| 초본 | rotate | 명조 | 0.0058 | 2/4 | 1.266 | 0.989 |
| 초본 | jpeg | 명조 | 0.0000 | 4/4 | 1.261 | 0.978 |
| 초본 | phone_weak | 명조 | 0.0058 | 0/4 | 1.335 | 0.957 |
| 초본 | phone_weak+rectified | 명조 | 0.0058 | 2/4 | 1.512 | 0.991 |
| 초본 | phone_strong | 명조 | 0.0174 | 1/4 | 1.298 | 0.913 |
| 초본 | phone_strong+rectified | 명조 | 0.0174 | 1/4 | 1.506 | 0.913 |
| 납부 | clean | 명조 | 0.0000 | 6/6 | 1.248 | 0.997 |
| 납부 | scan300 | 명조 | 0.0000 | 6/6 | 1.338 | 0.989 |
| 납부 | blur | 명조 | 0.0000 | 6/6 | 1.200 | 0.990 |
| 납부 | noise | 명조 | 0.0000 | 6/6 | 1.288 | 0.993 |
| 납부 | rotate | 명조 | 0.0000 | 6/6 | 1.150 | 0.996 |
| 납부 | jpeg | 명조 | 0.0000 | 6/6 | 1.157 | 0.990 |
| 납부 | phone_weak | 명조 | 0.0127 | 3/6 | 1.172 | 0.968 |
| 납부 | phone_weak+rectified | 명조 | 0.0000 | 6/6 | 1.427 | 0.995 |
| 납부 | phone_strong | 명조 | 0.0127 | 2/6 | 1.232 | 0.937 |
| 납부 | phone_strong+rectified | 명조 | 0.0127 | 2/6 | 1.398 | 0.937 |
| 가입 | clean | 명조 | 0.0000 | 6/6 | 1.215 | 0.996 |
| 가입 | scan300 | 명조 | 0.0000 | 6/6 | 1.427 | 0.994 |
| 가입 | blur | 명조 | 0.0000 | 6/6 | 1.175 | 0.991 |
| 가입 | noise | 명조 | 0.0000 | 6/6 | 1.258 | 0.990 |
| 가입 | rotate | 명조 | 0.0000 | 6/6 | 1.166 | 0.997 |
| 가입 | jpeg | 명조 | 0.0000 | 6/6 | 1.201 | 0.989 |
| 가입 | phone_weak | 명조 | 0.0122 | 0/6 | 1.321 | 0.936 |
| 가입 | phone_weak+rectified | 명조 | 0.0000 | 6/6 | 1.603 | 0.999 |
| 가입 | phone_strong | 명조 | 0.0183 | 0/6 | 1.357 | 0.945 |
| 가입 | phone_strong+rectified | 명조 | 0.0183 | 0/6 | 1.499 | 0.945 |

새 세트의 비영 CER는 정규화 확대 없이 유지했다. 명조 초본 clean/scan300/rotate에서 `-→–` 각 1개, blur에서는 4개였다. 약한 휴대폰에서는 배경/모서리의 가짜 `2/L/0` 등이 삽입되었다. 강한 명조 초본의 최종 CER .0174는 `-→–` 1개와 `∅→I`, `∅→-` 각 1개다. 이런 실제 OCR 출력 오류를 제거하지 않았다. 약한 명조 초본 보정 후에도 `-→−`가 남아 필드는 2/4다.

### 휴대폰과 보정 비교

`적용 X`는 외곽 사각형 검출 실패로 동일 원본을 OCR한 경우이며 성공한 보정으로 해석하면 안 된다. 검출은 약 6/6, 강 0/6이었다. 강한 조건은 현재 임계값·윤곽 사각형 조건을 충족하지 못했다. 실패를 숨기거나 정답 모서리로 대체하지 않았다. 따라서 **기본 엔진에 넣지 않는다**.

| 서류 | 글꼴 | 강도 | 보정 적용 | CER 전→후 | 필드 전→후 | 초/쪽 전→후 |
|---|---|---|---|---|---|---|
| 초본 | 고딕 | phone_weak | O | 0.0058→0.0000 | 1/4→4/4 | 1.142→1.430 |
| 초본 | 고딕 | phone_strong | X | 0.0116→0.0116 | 0/4→0/4 | 1.124→1.440 |
| 납부 | 고딕 | phone_weak | O | 0.0063→0.0000 | 2/6→6/6 | 1.220→1.508 |
| 납부 | 고딕 | phone_strong | X | 0.0127→0.0127 | 2/6→2/6 | 1.334→1.454 |
| 가입 | 고딕 | phone_weak | O | 0.0061→0.0000 | 1/6→6/6 | 1.274→1.522 |
| 가입 | 고딕 | phone_strong | X | 0.0122→0.0122 | 0/6→0/6 | 1.387→1.529 |
| 초본 | 명조 | phone_weak | O | 0.0058→0.0058 | 0/4→2/4 | 1.335→1.512 |
| 초본 | 명조 | phone_strong | X | 0.0174→0.0174 | 1/4→1/4 | 1.298→1.506 |
| 납부 | 명조 | phone_weak | O | 0.0127→0.0000 | 3/6→6/6 | 1.172→1.427 |
| 납부 | 명조 | phone_strong | X | 0.0127→0.0127 | 2/6→2/6 | 1.232→1.398 |
| 가입 | 명조 | phone_weak | O | 0.0122→0.0000 | 0/6→6/6 | 1.321→1.603 |
| 가입 | 명조 | phone_strong | X | 0.0183→0.0183 | 0/6→0/6 | 1.357→1.499 |

| 집계(6쪽 단순 평균 CER) | CER | 필드 합계 | 초/쪽 평균 |
|---|---:|---:|---:|
| phone_weak | 0.0082 | 7/32 | 1.244 |
| phone_weak+rectified | 0.0010 | 30/32 | 1.500 |
| phone_strong | 0.0141 | 5/32 | 1.289 |
| phone_strong+rectified | 0.0141 | 5/32 | 1.471 |

### 최종 회귀 검증 (기준 906ec68)

| 검증 | 통과 | 실패 |
|---|---:|---:|
| engine_v2 pytest | 108 (기존 85 + 신규 23) | 0 |
| run_p11_criteria_scenarios.py | 38 | 0 |
| run_p12_subsidy_criteria_scenarios.py | 29 | 0 |
| run_p13_household_scenarios.py | 26 | 0 |
| run_p14_pdf_forms_scenarios.py | 8 서식 | 0 |
| run_p15_jbai_scenarios.py | 129 | 0 |
| run_p2_scenarios.py | 53 | 0 |
| run_p3_scenarios.py | 150 | 0 |
| run_p4_scenarios.py | 182 | 0 |
| run_p5_scenarios.py | 152 | 0 |
| run_p6_scenarios.py | 249 | 0 |
| run_p7_scenarios.py | 238 | 0 |
| run_p8_localocr_scenarios.py | 89 | 0 |
| run_p9_identity_scenarios.py | 85 | 0 |
| tsc -b | 성공 | 0 |
| oxlint | 성공 (기존 StatusBadge.tsx 경고 1) | 0 |
| vite build | 성공 (기존 큰 청크 안내) | 0 |
| 새 합성 own 벤치 | 60 실행 | 0 엔진 오류 |

시나리오는 요청된 중단하지 않는 반복문을 그대로 실행하고 stdout/stderr를 로그로 보관해 파일별 집계했다. 샌드박스 TestClient 정지는 환경 문제로 외부 실행하여 완료했다. 기존 테스트 파일·demo/backend·판정/점수/추출기·공용 `.trellis/spec/`는 변경하지 않았다. 실서류·모델·글꼴·생성물은 커밋하지 않는다. 합성 시험의 더 낮은 필드 성공률은 강화된 신규 입력 조건에서 드러난 한계이며, 기존 85개 테스트와 기존 21쪽 기준 동작은 유지했다.

## 대시 정규화와 4대보험 발급일 (2026-11-11)

`extractors/format_text.py:normalize_format_text`는 U+2010~2015, U+2212, U+FE58, U+FE63, U+FF0D만 ASCII `-`로 옮기는 길이 보존 함수다. 날짜·주민번호·문서확인번호·연월 형식 매칭 직전 복사본에만 적용한다. 초본은 직접 사용하고, NHIS 공통 날짜/생년월일 파서, 납부확인서 연월 파서, 자격득실확인서의 공용 날짜 호출과 4대보험 파서가 공유한다. 현재 이 다섯 추출기에는 전화번호 파서가 없다. 새로운 전화번호 추출이나 허용 형식 확장은 추가하지 않는다.

슬래시·점은 변환하지 않는다. 초본 주소 이력 날짜는 기존 `-`/`.` 문법을 유지하며 `/`를 새로 허용하지 않는다. NHIS의 기존 `/` 허용은 유지한다. 전각 슬래시·전각 점·가운뎃점 등은 허용하지 않는다. 성명·주소·사업장명·금액 판정에는 정규화를 적용하지 않고 OCR 원문·근거 상자는 보존한다. 4대보험의 기존 주민번호 원문 즉시 폐기와 공용 가림 함수도 유지한다.

`extractors/insurance_issue.py:select_issue_date`는 기존 4대보험 서식의 머리 표(페이지 y 18~28%, 라벨 x 50% 이상)에서 `발급일시` 라벨을 찾는다. 공백·콜론 변형과 나뉜 라벨/합쳐진 OCR 영역을 지원한다. 라벨 오른쪽 같은 행의 칸만 검사하며 다음 라벨에서 멈춘다. 행 허용 폭은 작은 글자 높이로 제한해 큰 도장 상자가 주변 행을 끌어들이지 않게 한다. 도장·본문·왼쪽 날짜·아래 행은 발급일 후보로 사용하지 않는다. 다른 서식의 라벨 별칭을 추측하거나 OCR 오자를 교정하지 않는다.

오른쪽 칸 전체가 유효한 날짜 또는 날짜+시각이어야 한다. OCR이 날짜와 시각 사이 공백을 없앤 경우에도 전체 `YYYY-MM-DDHH:MM` 또는 초 포함 시각이 명확히 맞을 때만 날짜를 분리한다. 시각은 00~23시/00~59분·초 형식, 날짜는 실제 달력 날짜여야 한다. 라벨 누락, 빈칸, 깨진 형식, 복수 라벨/날짜는 값 없음으로 남긴다. 기존 `발급일_consistent`, `issue_not_future`, `dates_not_after_issue` 실패와 담당자 확인 경로를 그대로 사용한다. 신뢰도 공식·판정·점수 규칙은 바꾸지 않는다. 고정 머리 표 범위를 벗어난 서식은 추측하지 않고 담당자 확인이 필요하다.

NHIS `header_for_page`의 발급일 선택/납부확인서 확인문 날짜 대체 경로는 4대보험 선택기를 호출하지 않는다. main `92eadc2`와 정상 합성 입력 5종(초본, 납부 일반/요양 분리/확인문 발급일, 자격득실)을 비교해 모든 필드·원문 근거·상자·신뢰도·검증·경고가 동일함을 확인했고 새 테스트에 기준 스냅샷을 고정했다. 대시가 있는 입력의 형식 인식만 회복한다. 기존 조회기간 오선택 등 별도 NHIS 레이아웃 문제는 이 수정의 대상이 아니다.

### 합성 재현 결과

기존 D 생성기 `make_synth_eval.render`/`extract_diag.synthetic_cases`와 seed `20261111`을 재사용했다. 단위 테스트는 가짜 `OcrWord`, 통합 테스트는 실제 CPU own OCR을 사용한다. 모델·글꼴이 없으면 설치 이유와 명령을 표시하고 통합 테스트를 skip한다. 실서류는 사용하지 않았다.

| 조건 | 수정 전 | 수정 후 |
|---|---:|---:|
| (a) 발급일 대시 10종, 가짜 OCR | 0/10 | 10/10 |
| (b) 왼쪽 같은 행/근처 큰 도장, 가짜 OCR | 오선택 | 오른쪽 값 선택 |
| (c) 빈칸/깨진 칸 + 도장, 가짜 OCR | 도장으로 대체 | 값 없음·검증 실패 |
| (d) 라벨 누락 + 도장, 가짜 OCR | 값 없음 | 값 없음·검증 실패 |
| (e) 초본 주민번호/이력 대시 10종, 가짜 OCR | 형식 실패 | 이름·생년월일·이력 회복 |

명조 초본 실제 own 재측정은 동일 이미지·seed·열화 조건에서 수행했다. 이름/생년월일은 주민번호 대시가 선호 추출 경로를 막아 함께 실패했던 것이며, 성명 문자 자체를 바꿔 복원한 것이 아니다.

| 명조 초본 조건 | 수정 전 필드 | 수정 후 필드 | 회복한 필드 |
|---|---:|---:|---|
| clean | 2/4 | 4/4 | 이름·생년월일 |
| scan300 | 2/4 | 4/4 | 이름·생년월일 |
| rotate | 2/4 | 4/4 | 이름·생년월일 |
| blur | 3/4 | 4/4 | 주소이력 건수 |

네 조건 모두 4/4로 회복했다. 이 네 합성 조건에서는 대시 형식 처리가 남은 실패의 원인이었다. 휴대폰 원근 등 다른 조건이나 실서류의 원인이 같다는 뜻은 아니다.

```bash
.venv/bin/python -m pytest engine_v2/tests/test_format_parsing.py engine_v2/tests/test_own_format_integration.py -q
```

### 값 없는 발급일 안전 진단 (Mac)

아래 명령은 Mac의 사용자가 명시한 파일 한 개에만 적용하는 예시다. 이 작업 환경에서는 해당 위치를 만들거나 읽지 않았다.

```bash
.venv/bin/python -m engine_v2.tools.extract_diag \
  <4대보험 PDF 경로> \
  --doc insurance_4 --engine own --safe-issue
# 같은 파일에서 --engine applevision으로 바꿔 비교할 수 있다.
```

새 `--safe-issue`는 숫자·불리언·고정 분류명만 출력한다. 출력 키는 `SAFE_ISSUE_KEYS`, 구분 문자 분류는 `SEPARATOR_CLASSES`의 코드 허용 목록으로 고정한다. 값·인식 문구·파일명·입력 경로·좌표·정답은 출력하지 않는다. `--gt`, `--unmasked-synthetic`, `--synthetic-suite`와 함께 사용할 수 없다. 라이브러리의 Python/native 출력은 버리고 예외는 고정 실패 코드로 바꾼다. `--output`은 같은 안전 JSON만 저장하며 콘솔에는 `{"ok": true}`만 출력한다. 기존 일반 진단의 마스킹된 좌표 출력과 구별되는 엄격한 모드다.

`issue_label_found`는 라벨 인식, `right_cell_present`는 오른쪽 내용 존재, `right_cell_date_format`은 유효한 날짜/시각 형식, `selected_via_label`은 라벨 경로로 선택할 수 있었는지를 뜻한다. `header_date_candidate_count`는 상단 y≤28%의 날짜 모양 개수이며 유효 날짜 수나 실서류 정확도가 아니다. `stamp_date_candidate_present`는 그중 왼쪽 x≤50% 영역 날짜 모양 존재 여부로, 도장 자체를 인식했다는 뜻은 아니다. `separator_counts`는 그 날짜 모양 안의 원래 구분 문자 분류별 개수다.

예를 들어 라벨과 빈 오른쪽 칸, 왼쪽 슬래시 날짜 하나를 넣은 합성 출력에는 `issue_label_found=true`, `right_cell_present=false`, `right_cell_date_format=false`, `header_date_candidate_count=1`, `stamp_date_candidate_present=true`, `selected_via_label=false`, `SLASH=2`만 나타나며 실제 값은 없다. 테스트는 가짜 개인정보·날짜·파일명 및 native 출력이 결과 전체에 없는지 검사한다.

이번 수정의 최종 검증: pytest 222 통과/실패 0/skip 0(기존 147 + 신규 75), 시나리오 13개 모두 기준과 같은 통과 수/실패 0, 프론트 설치·타입 검사·lint·빌드 성공. 기존 Fast Refresh 경고 1건과 큰 청크 안내는 동일하다. 기존 테스트·demo/backend·README 세 파일·Trellis spec/workflow는 수정하지 않았다.
