# 합성 재현과 코드 조사

## 조사 환경과 실험 경계
- 일자: 2026-11-13 KST. 소스 기준: e63bdb6 (main/origin/main, PR #26 merge). PR #24라는 역사적 귀속 자체는 별도로 검증하지 않았고 현재 트리의 동작을 조사했다.
- 실행: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python /tmp/acq-loss-nhis-plan/probe.py`, 같은 방식의 `extra.py`.
- 산출: /tmp/acq-loss-nhis-plan/{probe.py,extra.py,synthetic-nhis.pdf,control.pdf,cells.json,results.json,extra-results.json,stdout.txt,stderr.txt,extra-stdout.txt,p4.db,storage/}. 스크립트·PDF·DB는 저장소에 넣지 않았다.
- PyMuPDF 기본 cjk 글꼴과 TextWriter로 A4 1쪽 글자층 PDF를 만들었다. 쪽 표시·발급번호·확인청구자 표·이력 열·확인 문장·라벨 없는 날짜·이사장·안내 3줄을 배치하고, 이력 내용은 PDF 삽입 순서 맨 뒤에 뒀다. QR은 사각형 자리 표시이며 실제 QR 판독은 하지 않는다.
- 합성 값: 가짜이름, 900101-1******, 가짜상사 (FAKE,Corp), G000000000000000000. 발급일/공고일/입력일 모두 2026-03-03. 최신 직장→지역→직장피부양자 3행과 이하여백을 배치했다. 글자층 359자이므로 사용자 관찰의 약 600자 원본과 동일 파일은 아니다.
- 좌표 쪽 데이터도 별도로 구성했다. 595×842 좌표계의 PageImage와 OcrWord를 사용하며 토큰 폭은 합성 근사값이다. 실제 PDF에서 _load_pages로 얻은 좌표와도 핵심 성명 오독을 교차 확인했다.
- ENGINE_V2_OCR=off로 실행했다. 글자층은 이 설정에도 LocalOcr의 지원 서류 추출 경로를 타고 own OCR을 호출하지 않는다(localocr.py:438,455; engine_v2/engine.py:174).
- 기존 테스트의 _isolate 방식으로 DB와 업로드 저장소를 /tmp에 바꾸고, 공통 STORAGE도 격리했다(demo/backend/tests/run_p4_scenarios.py:856). TestClient 수명주기에서 임시 DB를 초기화했다. 합성 신청자 신원은 ORM에 직접 넣고 업로드 API는 실제 HTTP 클라이언트로 호출했다. 인증 API 자체는 이번 실험 대상이 아니다.

## 실제 호출 결과
직접 read_document는 판독만 하므로 상태는 별도 check_document를 동일 요건/신원으로 호출해 기록했다. 업로드 결과의 상태/경고는 실제 API 응답이다. 저장된 OCR JSON에서 계층·엔진·필드를 확인했다.

| 실험 | 계층 / 엔진 | 종류 | 발급일 / 성명 / 생년월일 | 판독검증 | 상태·경고 |
|---|---|---|---|---|---|
| 직접: expected 없음 | localocr / pdftext | 자격득실 | 있음 / 없음 / 있음 | 8/8 | 자격확인 슬롯 FAIL: WRONG_DOCUMENT_TYPE; 자격득실 슬롯 PASS, 경고 없음 |
| 직접: expected 자격확인 | localocr / pdftext | 자격득실 | 있음 / 없음 / 있음 | 8/8 | 위와 동일 |
| 직접: expected 자격득실 | localocr / pdftext | 자격득실 | 있음 / 없음 / 있음 | 8/8 | 위와 동일 |
| 실제 업로드: 자격확인 슬롯 | localocr / pdftext | 자격득실 | 있음 / 없음 / 있음 | 8/8 | FAIL: WRONG_DOCUMENT_TYPE |
| 실제 업로드: 자격득실 슬롯 | localocr / pdftext | 자격득실 | 있음 / 없음 / 있음 | 8/8 | PASS, 경고 없음 |
| 같은 바이트·임의 파일명 업로드 | localocr / pdftext | 자격득실 | 있음 / 없음 / 있음 | 8/8 | FAIL: WRONG_DOCUMENT_TYPE |
| 대조: 제목만 자격확인서로 바꿈 | pdftext / pdftext | 자격확인 | 없음 / 없음 / 없음 | 필드 없음 | NEEDS_REVIEW: REQUIRED_FIELD_UNREADABLE, NHIS_SUBSCRIBER_IDENTITY_REVIEW |
| 통제: 원래 PDF + LocalOcr 예외 강제 | pdftext / pdftext | 자격득실 | 없음 / 없음 / 없음 | 필드 없음 | FAIL: WRONG_DOCUMENT_TYPE |

- 정상 LocalOcr 신뢰도 0.90, PdfText 대조군 0.85. PDF SHA256과 업로드 저장 파일 SHA256을 results.json에 남겼다. 동일 바이트 업로드 4건 모두 입력 해시와 같았다.
- 제목을 바꾼 대조군은 요청한 공단 자격득실 서류가 아니다. 이 대조군에서만 화면 종류·두 경고·상태 조합을 재현했으며 원래 문제의 원인이 입증됐다는 뜻이 아니다.
- 추가 좌표 실험 7건: 정상, 마커 제거, 번호 2→9, 성명 제거, 성명 값 x 이동, 긴 사업장명, 발급일 제거. 발급일 제거 외에는 성명 머리글 오독과 8개 검증 통과가 유지됐다. 발급일 제거는 발급일/5년 검증이 실패한다. 이는 마커·행 번호 검사가 없다는 코드 조사와 일치한다.
- 정식 회귀 시험은 이번 계획 단계에서 실행하지 않았다. 위 결과는 합성 조사 실험이며 pytest 통과 수가 아니다.

## 확인된 원인과 미확인 후보
### 성명 미출력인데 검증 통과
1. nhis_common.header_for_page는 성명 라벨 오른쪽의 같은 줄 단어를 먼저 보고, 후보가 있을 때 아래 값 행으로 내려가지 않는다(engine_v2/extractors/nhis_common.py:138). 옆 칸의 공백 있는 주민등록번호 라벨을 inline 성명 후보로 쓰고, 제외 목록도 주민등록번호 전체를 배제하지 않는다(:149,:158).
2. 합성 PDF 원시 추출과 좌표 원시 추출 모두 성명 값이 주민등록번호였다. 동일한 잘못된 값이 일관되므로 성명_consistent와 page_names_match가 통과했다(nhis_acquisition_loss.py:230,:247).
3. read_document 마지막에서 header-only 안전 검사로 성명 필드를 삭제한다(demo/backend/ocr/__init__.py:76; engine_v2/pipeline/field_safety.py:12,:47). 이미 만들어진 판독검증 문자열과 신뢰도는 다시 계산하지 않는다. localocr._from_nhis는 존재하는 필드의 최저 신뢰도로 계산한다(demo/backend/ocr/localocr.py:190,:196).
4. 일반 compare는 없는 필드를 건너뛰어 신원 경고가 없고, 올바른 자격득실 슬롯에서는 PASS가 가능했다(demo/backend/rules/identity.py:39; doc_check.py:612).
5. 이번 단쪽 합성에서는 검증이 8개다. 번호 비교는 2개 이상 읽혔을 때만 추가한다(nhis_acquisition_loss.py:251). 사용자 관찰의 9/9와 다른 원인은 이 실험만으로 확정하지 못했다(추정: 원본의 번호 단서·실행 버전·입력 구조 차이).

### 화면 결과와 직접 호출 차이
- 화면 문자열은 슬롯 이름이 아니라 doc.detected_doc_type이다(demo/frontend/src/pages/applicant/DocumentUpload.tsx:123). API document_dict는 d.doc_type을 넘기고(common.py:211), _save_row는 ocr.detected_doc_type을 저장한다(documents.py:233). to_engine_document의 doc_type은 요구 종류이지만 이것이 표시값을 덮어쓰지는 않는다(doc_check.py:218).
- 별개 enum 종류(doc_types.py:30), 자격확인 슬롯과 자격득실 슬롯은 각각 생성되고 둘 다 제출하라고 명시한다(required_docs.py:368,:378). accepts는 명시적 doc_type_choices 포함 여부다(:109). 기본 두 슬롯은 대체 제출을 허용하지 않는다. 추가서류의 복수 accepted 종류 설정 기능은 존재하지만 기본 NHIS 슬롯에는 적용되지 않는다(:330; api/common.py:97).
- 업로드는 expected=req.doc_type으로 read_document를 호출한다(documents.py:378). LocalOcr와 PdfText는 expected를 폐기한다(localocr.py:420; pdftext.py:395). 이번 3개 expected 비교도 동일 결과다. 슬롯 기대값이 종류를 바꿨다는 설명은 현재 코드와 실험에서 지지되지 않는다.
- Fixture는 stem 정확 일치다(demo/backend/ocr/fixture.py의 FixtureOcr.read). 이번 합성 파일명은 fixture 키를 사용하지 않았다. 사용자도 원래 파일명은 키와 다르다고 확인했다.
- LocalOcr는 import 실패/페이지 로드 실패 시 None을 반환하고, 밖으로 나온 일반 예외는 사슬이 잡아 다음 계층으로 진행한다(localocr.py:452,:463; ocr/__init__.py:47). 일반 예외는 fallback_reason에도 남기지 않는다. 따라서 PdfText로의 이동은 코드상 가능하다.
- PdfText는 제목에서 자격득실을 자격확인보다 먼저 찾고, 라벨 없는 발급일은 읽지 않는다(pdftext.py:33,:107,:124). 따라서 LocalOcr 실패만으로는 종류가 자격확인으로 바뀌는 것까지 설명할 수 없다. 강제 예외 실험에서도 자격득실 종류는 유지됐고 종류 오류가 먼저 반환되어 두 경고는 없었다(doc_check.py:320,:341).
- 두 경고의 실제 조건은 pdftext 계층+발급일 부재+날짜 요건(doc_check.py:346), 납부/자격확인으로 판별되어 성명 미판독(doc_check.py:541; identity.py:85)이다. 제목 변경 대조군은 이 조건을 모두 충족했다.
- 원래 화면의 원인은 미확정. 추정 후보: 서버/클라이언트 버전 차이, 실제 저장 바이트나 선택한 문서 ID 차이, PDF 텍스트 추출/제목 단서 차이, 실행 환경의 LocalOcr 실패. 각각 소스 버전·파일 해시·문서 ID·계층별 결과를 값 없이 비교해야 한다. 원본 접근 없이 이번 범위에서 더 확정할 수 없다.

## 현재 필드·신원·날짜 동작
| 항목 | 현재 코드와 결과 |
|---|---|
| 성명 | nhis_common.py:138의 성명 라벨 주변 탐색. 공단의 옆 라벨을 값으로 읽는 결함은 위에서 재현. |
| 생년월일 | nhis_common.py:163의 주민등록번호 라벨 주변 탐색과 :189 마스킹 정규식. :198에서 3/4/7/8→2000, 1/2/5/6→1900. 합성 공단에서는 성공했으므로 실패라고 단정하지 않는다. 라벨 아래 탐색은 3줄/6% 이내로 제한(:173). |
| 발급일 | nhis_common.py:228의 라벨 날짜, 없으면 page_headers(:235)에서 마지막 쪽의 _closing_issue_date(:245). 확인합니다 다음·이사장 직전의 날짜 단독 줄, 주변 다른 날짜와 충돌 없음(:274). 공단 합성에서도 성공. PdfText만 타면 실패(pdftext.py:124). |
| 발급번호 | nhis_acquisition_loss.py:93은 문서확인번호 근처 숫자 12~20자리만 읽는다. G+18자리/발급번호는 지원하지 않고 :251 비교도 2개 이상일 때만. 번호 원문은 결과 필드로 노출하지 않는 기존 회귀(test_nhis_continuation_identity.py:66)를 유지할 설계가 필요. |
| 이력 | nhis_acquisition_loss.py:124, :166에서 좌표상 날짜 열 중심 거리로 취득/상실 구분. 사업장은 :185에서 employer 헤더 중심 오른쪽 모든 단어를 붙여 날짜도 섞고 왼쪽에서 시작한 긴 사업장 단어는 누락한다. 합성 좌표 지역 빈 사업장에 날짜 문자열이 들어갔다. 번호·마커 검사는 없다(:268,:300). |
| 이어지는 쪽 | 첫 쪽 신원을 요구하고 관찰된 후속 신원만 비교(:82), 발급일은 관찰된 합의(:234), 문서확인번호는 두 개 이상일 때 비교(:251). 정부24 페이지 수 검증을 완성된 공통 기능으로 가정하면 안 된다. |
| 신원 | doc_check.py:541의 가입자 가족 대조는 납부/자격확인만. _refresh_nhis_identity도 이 둘만 수집(documents.py:253). 자격득실은 :612 일반 compare로, 미판독은 건너뛰고 확실한 불일치는 FAIL(:616). 전용 검토 분기가 필요. |
| 공고일 당일 | criteria.py:189는 공고일 자체를 최소 날짜로 넘긴다. engine/stage1_document_check.py:45는 issue_date < min_issue_date만 거절한다. 즉 현재 의미는 공고일 이상(당일 통과). 합성 정상의 날짜 오류도 없었다. 정책 변경은 미확정이다. |

## 기존 합성·시험 관례
- demo/backend/tests/run_p2_scenarios.py:64은 cjk TextWriter 글자층 PDF를 임시 경로에 만든다. 이번 PDF가 이를 따른다.
- engine_v2/tools/make_synth_eval.py:70의 render는 좌표 셀을 렌더링하고 지정 글꼴 또는 cjk를 쓴다. :205의 생성기는 학습/시험 글꼴 분리와 자산 확인 후 출력한다.
- engine_v2/tests/test_own_format_integration.py:16의 _available은 모델/런타임 부재를 skip하고, font_path 실패도 :26에서 synthetic font absent로 skip한다. 이 관례는 이미지 OCR 통합에만 적용하고 좌표 단위 시험은 글꼴과 무관하게 필수 실행한다.
- engine_v2/tests/test_nhis_extractors.py:13와 test_nhis_continuation_identity.py:10는 OcrWord+PageImage 좌표 단위 시험을 구성한다. 기존 이어지는 쪽/번호/정체성 회귀를 삭제하거나 약화하지 않는다.

## 실험 재확인 메모
- 직접 판독 3건, 업로드 5건, 좌표 변형 7건, 실제 PDF 원시 추출 교차 확인 1건을 수행했다. 정상/마커 없음/번호 불연속/성명 없음/성명 위치 이동/긴 사업장 좌표 실험은 각각 8/8, 하단 날짜 없음은 6/8이었다.
- 실행 스크립트 SHA256: probe.py `c4f6e389125e52366fdb1b7dde3c882176b46d8bcd1250586feecfdac4c9a0ba`, extra.py `63fab8d9a6e6db4d17e96f4197f627e06dc90dceb9a8ad5840fa1b2a810ff3f8`.
- /tmp 파일은 일시 자료다. 영구 산출물은 이 조사 기록과 설계이며 스크립트 자체는 커밋하지 않는다.
