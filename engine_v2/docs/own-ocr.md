# 자체 OCR 1단계

`own`은 공개 사전학습 PP-OCR 모델을 기관 내부 CPU에서 ONNX Runtime으로 추론하는 엔진이다. 직접 사전학습한 모델이라는 뜻은 아니다. 2단계에서 전북 서류 합성 데이터로 추가 학습한다. 이번에는 미세조정, 판정·점수 규칙 변경, demo 백엔드 연결을 하지 않았다.

## 기존 구조와 호환 계약

기존 `pipeline/ocr.py`를 `pipeline/ocr/__init__.py`로 이동했다. `engine_v2.pipeline.ocr` import와 `run_ocr(engine, png, size)` 인터페이스는 유지한다. Apple Vision은 정규화된 좌하단 좌표를 좌상단 픽셀로 변환하고, EasyOCR/Paddle은 다각형의 외접 사각형을 반환한다. `OcrWord(text, confidence, bbox_px)`의 confidence는 0~1, 좌표는 입력 이미지의 좌상단 원점 `(x0,y0,x1,y1)`이다. 텍스트 읽기 순서는 기존의 `(round(y0/15), x0)`를 따른다. 기존 세 추출기는 수정하지 않았다.

`own`은 DB 확률맵 → 윤곽선/영역 평균 점수 → polygon unclip → 원본 좌표 복원 → 원근 보정 crop → Korean CTC 순이다. 검출은 긴 변 최대 1600, 32배수 크기; 인식은 높이 48, 최소 폭 320이다. DB 임계값 0.3/box 점수 0.5/unclip 1.5를 고정했다. 세로 crop은 회전하지만 180도 방향 분류 모델은 포함하지 않는다. CPUExecutionProvider만 사용하며 스레드는 intra=2/inter=1이다. 네트워크 다운로드는 fetch 명령에서만 수행한다. 추론 시작 시 모든 파일 해시, 사전·출력 클래스 수, 모델 내장 문자 목록을 검증한다.

`engine_v2.engine.run`과 CLI는 `ENGINE_V2_OCR`를 우선하고, 없으면 macOS=`applevision`, 그 외=`own`이다. **demo/backend의 기존 비맥 easyocr 기본값은 변경하지 않았다.** 해당 기본값은 그 디렉터리에 있으므로 변경 금지/체인 연결 제외 조건을 우선했다. demo 연결은 후속 작업이다.

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

## 평가 정의

기본 seed와 가짜 값으로 초본·납부확인서·4대보험 형태 3종 × 7열화 21쪽을 만든다. 같은 문서의 clean/scan300/blur/noise/rotate(±2도 이내)/jpeg/phone(원근·조명)을 비교한다. `demo.fixtures.make_samples`의 문구 및 CJK TextWriter 렌더링 관례를 재사용한다. 기존 templates는 신청서/동의서이므로 이 세 증명서의 공식 양식으로 오용하지 않는다. 4대보험 형태는 기존 `nhis_acquisition_loss` 계약을 시험하기 위해 건강보험 자격득실 부제·표를 포함하는 **복합 합성 서식**이다. 공식 4대보험 서식 대응을 입증하지 않는다.

CER: NFC 정규화 후 모든 Unicode 공백을 제거, 대소문자·문장부호 유지. Levenshtein 편집거리 / max(정답 글자 수, 1); 삽입이 많으면 1을 넘을 수 있다. 줄 정답은 렌더링 문구에서 독립적으로 작성한다. 필드 정확도는 기존 추출기의 직렬화된 필드값과 정답의 완전 일치 비율이며 누락도 오답이다. 문서 종류는 manifest의 평가 라우팅에만 사용하며 이미지 파일명으로 인식/판정하지 않는다.

평균 신뢰도는 인식 영역 점수의 단순 평균이다. 신뢰도 구간 [0,.5), [.5,.8), [.8,.9), [.9,1]별로 전체 정답과 예측 문자열을 편집 정렬하고, 출력 문자마다 해당 영역 점수를 부여하여 정답률/평균 신뢰도/표본 수를 계산한다. 삭제 문자는 CER에 포함하되 출력 신뢰도가 없어 구간에서 제외한다. 이것은 모델 자체의 문자 확률 보정 평가와 다르다. 점수는 판정 확률이 아니다.

시간은 첫 모델 로드가 포함된 한 번의 실행 wall time이며 별도 warm-up/반복 측정은 하지 않았다. 엔진 미설치/플랫폼 불일치/키 미설정은 skip으로 기록한다. 합성 출력도 기본적으로 기존 공용 `mask_text`를 사용한다. `--unmasked-synthetic`만 합성 결과의 텍스트 가림을 해제한다. 실서류 가림 함수 자체는 변경하지 않았다.

## 한계와 2단계

합성 3개 문서/한 폰트는 실제 서류 일반화 성능을 보장하지 않는다. 주민번호는 생년월일·성별 뒤 별표만 사용한다. 표의 작은 숫자, 회전/원근의 읽기 순서, 장문 crop, 180도 뒤집힌 입력, 직인/손글씨, 실제 복잡한 레이아웃은 추가 평가가 필요하다. `OcrWord`는 문자 하나가 아닌 검출 텍스트 영역이어서 셀 병합이 필드 추출 정확도에 영향을 준다.

2단계는 전북 서류의 다양한 합성 폰트·표·날짜·금액·주소를 늘리고, 템플릿/값/폰트 단위로 학습·검증·시험을 분리한다. Korean 인식 모델을 우선 미세조정하고 검출 모델은 누락 분석 후 별도 판단한다. 학습 환경의 Paddle 프레임워크는 추론 requirements와 분리한다. ONNX 재변환 후 고정 시험 세트의 CER/필드 정확도/지연/보정을 기존 모델과 비교하여 회귀가 없을 때만 교체한다. 실서류 평가는 별도의 승인된 내부 환경에서 수행한다.

## 합성 벤치 결과 (2026-11-11, WSL CPU)

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

## 회귀 검증

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
